[app]
title = MMA Chaveamento
package.name = mmachaveamento
package.domain = org.seunome

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,wav,mp3,ogg,json
source.include_patterns = assets/sons/*

version = 1.0

requirements = python3,kivy==2.3.1,pillow,plyer

orientation = portrait
fullscreen = 0

android.permissions = WAKE_LOCK

android.archs = arm64-v8a,armeabi-v7a
android.api = 34
android.minapi = 21
android.ndk = 25b

[buildozer]
log_level = 2
warn_on_root = 1