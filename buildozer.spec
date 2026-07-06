[app]

title = Tap Circle
package.name = tapcircle
package.domain = org.tapcircle
source.dir = .
source.include_exts = py,png,jpg,jpeg,mp3,wav,ogg,json
version = 1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.private_storage = True
android.theme = "@android:style/Theme.NoTitleBar"
android.archs = arm64-v8a, armeabi-v7a

[buildozer]

log_level = 2
warn_on_root = 1
