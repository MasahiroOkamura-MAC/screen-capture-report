#!/bin/bash

APP_NAME="ScreenCaptureReport"
APP_DIR="${APP_NAME}.app"
ICON_SOURCE="app_icon.png"
ICON_SET="app_icon.iconset"
SCRIPT_SOURCE="launcher.applescript"

echo "Building ${APP_NAME}..."

# 1. Clean up
if [ -d "$APP_DIR" ]; then
    rm -rf "$APP_DIR"
fi

# 2. Compile AppleScript (Creates the App Bundle)
echo "Compiling AppleScript..."
osacompile -s -o "$APP_DIR" "$SCRIPT_SOURCE"

if [ ! -d "$APP_DIR" ]; then
    echo "Error: Failed to create app."
    exit 1
fi

# 3. Handle Icons
if [ -f "$ICON_SOURCE" ]; then
    echo "Creating icons..."
    mkdir -p "$ICON_SET"
    
    # helper for sips
    # sips -z H W -s format png input --out output
    
    sips -z 16 16     -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_16x16.png"
    sips -z 32 32     -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_16x16@2x.png"
    sips -z 32 32     -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_32x32.png"
    sips -z 64 64     -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_32x32@2x.png"
    sips -z 128 128   -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_128x128.png"
    sips -z 256 256   -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_128x128@2x.png"
    sips -z 256 256   -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_256x256.png"
    sips -z 512 512   -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_256x256@2x.png"
    sips -z 512 512   -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_512x512.png"
    sips -z 1024 1024 -s format png "$ICON_SOURCE" --out "${ICON_SET}/icon_512x512@2x.png"

    # iconutil works on the directory
    echo "Converting to icns..."
    if iconutil -c icns "$ICON_SET" -o "$APP_DIR/Contents/Resources/applet.icns"; then
        echo "Icon applied successfully."
    else 
        echo "Warning: Icon generation failed."
    fi
    
    rm -rf "$ICON_SET"
else
    echo "Warning: No icon found at $ICON_SOURCE"
fi

# 4. Update Info.plist if needed (osacompile sets it up for applet)
# We can just leave it as is, or modify LSUIElement if we want to hide it later. 
# For now, standard applet behavior is fine.

echo "Done! ${APP_NAME} is ready."
