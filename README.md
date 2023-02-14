# Cross-platform kivy image picker

The maximum required number of functions for working with the image picker has been added to the example

## Usage and installation
Download python [directly](https://www.python.org/downloads/) or use [conda environment](https://www.anaconda.com/products/distribution)

```shell
git clone https://github.com/Neizvestnyj/cross-platform-image-picker.git
```

### Desktop:
```shell
cd cross-platform-image-picker
pip install -r requirements.txt
python main.py
```

### Android
You can build an android application only on a **Unix** system.
To build *apk* and *aab* use [buildozer](https://github.com/kivy/buildozer) and [p4a](https://github.com/kivy/python-for-android)

```shell
pip install buildozer
```

```shell
cd cross-platform-image-picker
buildozer android debug deploy run logcat
```

### iOS
To build iOS app use [kivy-ios](https://github.com/kivy/kivy-ios)

[kivy-ios installation](https://github.com/kivy/kivy-ios#installation--requirements)

```shell
toolchain build python3 kivy pillow plyer
```
