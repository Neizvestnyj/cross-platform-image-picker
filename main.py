from kivy.app import App
from kivy.utils import platform
from kivy.clock import mainthread, Clock
from kivy.weakproxy import WeakProxy
from kivy.properties import ListProperty
from kivy.logger import Logger, LOG_LEVELS
from kivy.event import EventDispatcher

from plyer import filechooser
import os
from shutil import copyfile
import tempfile
from PIL import Image
import time
from typing import Union

Logger.setLevel(LOG_LEVELS["debug"])

if platform == 'android':
    import jnius
    from jnius import autoclass, cast
    from android.permissions import check_permission, request_permissions, Permission
    from android import activity as android_activity
    from kivy.core.window import Window

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Activity = autoclass('android.app.Activity')
    currentActivity = cast(Activity, PythonActivity.mActivity)

    Context = autoclass("android.content.Context")
    context = cast(Context, currentActivity.getApplicationContext())

    Intent = autoclass('android.content.Intent')

    MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
    ImagesMedia = autoclass('android.provider.MediaStore$Images$Media')
    VideoMedia = autoclass('android.provider.MediaStore$Video$Media')
    AudioMedia = autoclass('android.provider.MediaStore$Audio$Media')

    ImageColumns = autoclass('android.provider.MediaStore$Images$ImageColumns')
    BitmapFactory = autoclass('android.graphics.BitmapFactory')
    Bitmap = autoclass('android.graphics.Bitmap')
    CompressFormat = autoclass('android.graphics.Bitmap$CompressFormat')

    File = autoclass('java.io.File')
    FileOutputStream = autoclass('java.io.FileOutputStream')
    FileInputStream = autoclass('java.io.FileInputStream')
    FileChannel = autoclass('java.nio.channels.FileChannel')
    ExifInterface = autoclass('android.media.ExifInterface')

    DocumentsContract = autoclass('android.provider.DocumentsContract')
    Environment = autoclass('android.os.Environment')

    Uri = autoclass('android.net.Uri')
    ContentUris = autoclass('android.content.ContentUris')

    Long = autoclass('java.lang.Long')


    def begone_you_black_screen(dt):
        Window.update_viewport()

else:

    def check_permission(*args):
        return True

if platform in ['linux', 'macosx']:
    # `tempfile.gettempdir()` - files deleted upon reboot
    tmp_path = os.path.join('/', 'var', 'tmp', 'TestApp')
else:  # platform in ['win', 'android']
    tmp_path = os.path.join(tempfile.gettempdir(), 'TestApp')

tmp_images_path = os.path.join(tmp_path, 'images')

if not os.path.exists(tmp_images_path):
    os.makedirs(tmp_images_path)

Logger.debug(f'tmp: {tmp_images_path}')


class BaseEventDispatcher(EventDispatcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_event_type('on_image_selected')

    def on_image_selected(self, path: str):
        pass


class ImagePicker(BaseEventDispatcher):
    selection = ListProperty([], allownone=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget = None

    def choose(self, widget: WeakProxy, **kwargs):
        self.widget = widget

        Logger.debug('ImagePicker start')

        filechooser.open_file(on_selection=self.file_selection, filters=[["Image", "*jpg", "*png", "*bmp", "*jpeg"]])

    def file_selection(self, selection):
        if selection:
            path = str(selection[0])
            if not os.path.exists(tmp_images_path):
                os.makedirs(tmp_images_path)

            filename = os.path.basename(path)

            tmp_file = os.path.join(tmp_images_path, filename)
            copyfile(path, tmp_file)

            Logger.debug(f'Image copied to tmp folder: {tmp_file}')
            Logger.debug(f'Image selected: {path}')

            self.widget.text = f'Temp: {tmp_file}\nReal: {path}'
            self.dispatch('on_image_selected', path)
        else:
            path = ''

        return path


class ImagePickerAndroid(BaseEventDispatcher):
    def __init__(self, pick_image: int = 1, *args, **kwargs):
        super().__init__(*args, **kwargs)

        android_activity.bind(on_activity_result=self.activity_for_result)

        self.pick_image = pick_image
        self.image_orientation = None
        self.widget = None

    def __del__(self):
        android_activity.unbind(on_activity_result=self.activity_for_result)

    @staticmethod
    def scan_file(path: str):
        """
        :param path:
        :return:
        We inform the gallery that there is a file with path - `path`
        Use it if you have placed the image outside the application folder
        (downloaded it to the download folder, for example)
        """

        MediaScannerConnection.scanFile(android_activity, [path], None, None)

    def choose(self, widget: WeakProxy, *args):
        """
        :param widget: for example label
        :param args:
        :return:
        """

        self.widget = widget

        if check_permission('android.permission.WRITE_EXTERNAL_STORAGE'):
            photoPickerIntent = Intent(Intent.ACTION_GET_CONTENT)
            photoPickerIntent.setType("image/*")  # must be mime type
            currentActivity.startActivityForResult(
                photoPickerIntent, self.pick_image)
            Clock.schedule_once(begone_you_black_screen)
        else:
            return

    def get_path(self, uri, method=1) -> str:
        """
        :param uri: `Uri` type
        :param method:
        :return:
        """

        file_path = ''

        if method == 1:
            # solution from https://stackoverflow.com/a/40844108/12938901
            if DocumentsContract.isDocumentUri(context, uri):
                # ExternalStorageProvider
                if "com.android.externalstorage.documents" == uri.getAuthority():
                    Logger.debug('ExternalStorageProvider')

                    docId = DocumentsContract.getDocumentId(uri)
                    split = docId.split(":")
                    file_path = Environment.getExternalStorageDirectory() + "/" + split[1]

                    return file_path

                # DownloadsProvider
                elif "com.android.providers.downloads.documents" == uri.getAuthority():
                    Logger.debug('DownloadsProvider')
                    docId = DocumentsContract.getDocumentId(uri)

                    try:
                        contentUri = ContentUris.withAppendedId(
                            Uri.parse("content://downloads/public_downloads"),
                            Long.valueOf(docId),
                        )
                        return self.getDataColumn(context, contentUri, None, None)
                    except jnius.jnius.JavaException as java_number_ex:
                        Logger.debug(f'{java_number_ex}')
                        # https://stackoverflow.com/a/60642994/12938901
                        # In Android 8 and Android P the id is not a number
                        return uri.getPath().replace('/document/raw:', '').replace('raw:', '')

                # MediaProvider
                elif "com.android.providers.media.documents" == uri.getAuthority():
                    Logger.debug('MediaProvider')

                    docId = DocumentsContract.getDocumentId(uri)
                    split = docId.split(":")
                    doc_type = split[0]
                    if 'image' == doc_type:
                        contentUri = ImagesMedia.EXTERNAL_CONTENT_URI
                    elif 'video' == doc_type:
                        contentUri = VideoMedia.EXTERNAL_CONTENT_URI
                    elif 'audio' == doc_type:
                        contentUri = AudioMedia.EXTERNAL_CONTENT_URI
                    else:
                        Logger.error(f'Cent specify document type: {doc_type}')
                        return ''

                    selection = "_id=?"
                    selectionArgs = [split[1]]

                    return self.getDataColumn(context, contentUri, selection, selectionArgs)
            # MediaStore (and general)
            elif "content" == uri.getScheme().lower():
                Logger.debug('MediaStore (and general)')

                # Return the remote address
                if "com.google.android.apps.photos.content" == uri.getAuthority():
                    return uri.getLastPathSegment()
            # File
            elif "file" == uri.getScheme():
                Logger.debug('File')
                return uri.getPath()
        else:
            # Bad solution
            media_data = [ImagesMedia.DATA]
            cursor = context.getContentResolver().query(uri, media_data, None, None, None)
            Logger.debug(f'cursor: {cursor}')

            if not cursor:
                file_path = uri.getPath()
            else:
                # if you use gallery or some thing like that
                cursor.moveToFirst()
                indx = cursor.getColumnIndexOrThrow(media_data[0])
                file_path = cursor.getString(indx)
                cursor.close()

        return file_path

    def getDataColumn(self,
                      context,
                      uri,
                      selection: Union[str, None],
                      selectionArgs: Union[list, None],
                      column: str = "_data"
                      ):
        """
        :param context: mContext
        :param uri: Uri
        :param selection:
        :param selectionArgs:
        :param column:
        :return:
        """

        Logger.debug(f'context {context}, uri {uri} selection: {selection} selectionArgs: {selectionArgs}')

        file_path = ''
        projection = [column]

        cursor = context.getContentResolver().query(uri, projection, selection, selectionArgs, None)
        if cursor is not None:
            cursor.moveToFirst()
            index = cursor.getColumnIndexOrThrow(column)
            file_path = cursor.getString(index)

            cursor.close()

        return file_path

    def activity_for_result(self, requestCode, resultCode, data):
        if resultCode != Activity.RESULT_OK:
            return

        # AttributeError: 'NoneType' object has no attribute 'compress'
        if requestCode == self.pick_image and Activity.RESULT_OK and data:
            try:
                self.get_image_orientation(data)
                # self.get_file_type(data)
                selected_image = data.getData()  # uri

                real_file_path = self.get_path(selected_image)

                Logger.debug(f'Real picture path: {real_file_path}')
                try:
                    inputStream = context.getContentResolver().openInputStream(selected_image)
                except jnius.jnius.JavaException as java_ex:
                    if 'java.io.FileNotFoundException' in str(java_ex):
                        Logger.error(str(java_ex))

                    Clock.schedule_once(begone_you_black_screen)
                    return

                pictureBitmap = BitmapFactory.decodeStream(inputStream)

                name = str(time.time()) + ".jpg"
                if not os.path.exists(tmp_images_path):
                    os.mkdir(tmp_images_path)

                # copy file to tmp folder, better to work with it
                file = File(tmp_images_path, name)
                fOut = FileOutputStream(file)

                try:
                    pictureBitmap.compress(CompressFormat.JPEG, 85, fOut)
                except AttributeError:
                    Logger.error('The image cannot be opened, it may be damaged')
                    fOut.close()
                    return

                fOut.close()

                file_path = os.path.join(tmp_images_path, name)

                file_size = os.path.getsize(file_path)  # image size

                if file_size > 15728640:  # check file size
                    Logger.warning('Big file. The image is too heavy')
                    return

                self.rotate_image(file_path)  # rotate image

                self.add_text(self.widget, f'Temp: {file_path}\nReal: {real_file_path}')

                Logger.debug(f'Image selected: {file_path} {file_size}')

                self.dispatch('on_image_selected', real_file_path if real_file_path else file_path)
            except Exception as err_java:
                Logger.error(f"Java error: {err_java}")
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE],
                                    callback=None,
                                    )

    @mainthread
    def add_text(self, widget, text: str):
        """
        :param widget: widget, that have attribute text (for example)
        :param text:
        :return:
        """

        widget.text = text

    def get_image_orientation(self, data):
        # get image orientation
        # be sure to open a new stream, otherwise an incorrect orientation will be obtained
        try:
            try:
                inputStream = context.contentResolver.openInputStream(data.getData())
            except jnius.jnius.JavaException as java_ex:
                # may be: No such file or directory
                Logger.error(f'inputStream error: {java_ex}')
                return

            exif = ExifInterface(inputStream)
            orientation = exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            Logger.debug(f'Image orientation: {orientation}')

            rotate_180 = [ExifInterface.ORIENTATION_ROTATE_180, ExifInterface.ORIENTATION_FLIP_VERTICAL]
            rotate_90 = [ExifInterface.ORIENTATION_TRANSPOSE, ExifInterface.ORIENTATION_ROTATE_90]
            rotate_minus_90 = [ExifInterface.ORIENTATION_TRANSVERSE, ExifInterface.ORIENTATION_ROTATE_270]

            if orientation in rotate_180:
                self.image_orientation = 180
            elif orientation in rotate_90:
                self.image_orientation = -90
            elif orientation in rotate_minus_90:
                self.image_orientation = 90
            else:
                self.image_orientation = None

            Logger.debug(f'Image rotation: {self.image_orientation}; orientation: {orientation}')

        except Exception as get_orientation_error:
            Logger.error(f'{get_orientation_error}')
            self.image_orientation = None

    @staticmethod
    def get_file_type(data):
        # get file type
        try:
            cr = context.getContentResolver()
            mimeType = cr.getType(data.getData())
            Logger.debug(f'MemeType: {mimeType}, {type(mimeType)}')
            return mimeType
        except Exception as get_type_err:
            Logger.error(f'{get_type_err}')

        return None

    def rotate_image(self, filename):
        if self.image_orientation:
            try:
                im = Image.open(filename)
                im_rotate = im.rotate(self.image_orientation)
                im_rotate.save(filename)
                im.close()
                Logger.debug(f'{filename} - rotated')
            except Exception as image_rotate_error:
                Logger.error(f'{image_rotate_error}\nfilename={filename}')


if __name__ == '__main__':
    from kivy.lang.builder import Builder
    from kivy.clock import mainthread

    KV = '''   
Screen:
    Image:
        id: img
        pos: self.pos
        size_hint: None, None
        size: root.size
        allow_stretch: True

    BoxLayout:
        orientation: 'vertical'
        spacing: dp(5)
        padding: dp(5)

        Label:
            id: lbl
            text: 'Path to image'
            text_size: self.width, None
            halign: 'center'
            color: (1, 0, 0, 1)
            markup: True


        Button:
            text: 'Open image picker'
            size_hint_y: None
            height: dp(50)
            opacity: 0.8
            on_release: app.open_file_manager()
    '''


    class TestApp(App):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

            if platform == 'android':
                self.picker = ImagePickerAndroid()
            else:
                # Windows, Linux, MacOS, ios
                self.picker = ImagePicker()

            self.picker.bind(on_image_selected=self.on_image_selected)

        def build(self):
            return Builder.load_string(KV)

        def on_start(self):
            if platform == 'android':
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE])

        def open_file_manager(self):
            self.picker.choose(self.root.ids.lbl)

        @mainthread
        def on_image_selected(self, inst, path: str):
            self.root.ids.img.source = path


    TestApp().run()
