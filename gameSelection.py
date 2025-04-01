import pygetwindow
import time
import bettercam
from typing import Union, Tuple, Any
import ctypes
import win32gui
import win32ui
import win32con
from PIL import Image
import numpy as np

# Could be do with
# from config import *
# But we are writing it out for clarity for new devs
from config import screenShotHeight, screenShotWidth

class Win32Camera:
    def __init__(self, region):
        self.region = region
        self.left, self.top, self.right, self.bottom = region
        self.width = self.right - self.left
        self.height = self.bottom - self.top
        self.hwnd = win32gui.GetDesktopWindow()
        self.is_running = False

    def start(self, target_fps=None, video_mode=None):
        self.is_running = True
        return True

    def stop(self):
        self.is_running = False

    def get_latest_frame(self):
        if not self.is_running:
            return None

        try:
            # Get device context
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            # Create bitmap
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, self.width, self.height)
            saveDC.SelectObject(saveBitMap)

            # Copy screen into bitmap
            saveDC.BitBlt((0, 0), (self.width, self.height), mfcDC,
                         (self.left, self.top), win32con.SRCCOPY)

            # Convert bitmap to numpy array
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype=np.uint8).reshape(self.height, self.width, 4)

            # Cleanup
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwndDC)

            return img

        except Exception as e:
            print(f"Error capturing frame: {str(e)}")
            return None

def get_screen_bounds():
    """Get the bounds of all screens combined"""
    user32 = ctypes.windll.user32
    total_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    total_height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
    min_x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    min_y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    return (min_x, min_y, total_width, total_height)

def create_capture(region: Tuple[int, int, int, int]) -> Union[Any, None]:
    """Try different capture methods"""
    # Try BetterCam first
    try:
        print("Attempting to create BetterCam capture...")
        camera = bettercam.create(region=region, output_color="BGRA", max_buffer_len=512)
        if camera is not None:
            return camera
    except Exception as e:
        print(f"BetterCam creation failed: {str(e)}")

    # Try dxcam
    try:
        print("Falling back to dxcam...")
        import dxcam
        camera = dxcam.create(region=region, output_color="BGRA")
        if camera is not None:
            return camera
    except Exception as e:
        print(f"dxcam creation failed: {str(e)}")

    # Fall back to Win32 capture
    try:
        print("Falling back to Win32 capture...")
        camera = Win32Camera(region)
        return camera
    except Exception as e:
        print(f"Win32 capture creation failed: {str(e)}")

    return None

def gameSelection() -> (Any, int, int | None):
    # Selecting the correct game window
    try:
        videoGameWindows = pygetwindow.getAllWindows()
        print("=== All Windows ===")
        for index, window in enumerate(videoGameWindows):
            # only output the window if it has a meaningful title
            if window.title != "":
                print("[{}]: {}".format(index, window.title))
        # have the user select the window they want
        try:
            userInput = int(input(
                "Please enter the number corresponding to the window you'd like to select: "))
        except ValueError:
            print("You didn't enter a valid number. Please try again.")
            return None, None, None
        # "save" that window as the chosen window for the rest of the script
        videoGameWindow = videoGameWindows[userInput]
    except Exception as e:
        print("Failed to select game window: {}".format(e))
        return None, None, None

    # Activate that Window
    activationRetries = 30
    activationSuccess = False
    while (activationRetries > 0):
        try:
            videoGameWindow.activate()
            activationSuccess = True
            break
        except pygetwindow.PyGetWindowException as we:
            print("Failed to activate game window: {}".format(str(we)))
            print("Trying again... (you should switch to the game now)")
        except Exception as e:
            print("Failed to activate game window: {}".format(str(e)))
            print("Read the relevant restrictions here: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow")
            activationSuccess = False
            activationRetries = 0
            break
        # wait a little bit before the next try
        time.sleep(3.0)
        activationRetries = activationRetries - 1
    # if we failed to activate the window then we'll be unable to send input to it
    # so just exit the script now
    if activationSuccess == False:
        return None, None, None
    print("Successfully activated the game window...")

    try:
        # Get screen bounds
        screen_bounds = get_screen_bounds()
        print(f"Total screen bounds: {screen_bounds}")

        # Starting screenshoting engine
        left = ((videoGameWindow.left + videoGameWindow.right) // 2) - (screenShotWidth // 2)
        top = videoGameWindow.top + \
            (videoGameWindow.height - screenShotHeight) // 2
        right, bottom = left + screenShotWidth, top + screenShotHeight

        # Ensure the region is within screen bounds
        min_x, min_y, max_width, max_height = screen_bounds
        left = max(min_x, min(left, min_x + max_width - screenShotWidth))
        top = max(min_y, min(top, min_y + max_height - screenShotHeight))
        right = left + screenShotWidth
        bottom = top + screenShotHeight

        region: tuple = (left, top, right, bottom)
        print(f"Attempting to capture region: {region}")

        # Calculating the center Autoaim box
        cWidth: int = screenShotWidth // 2
        cHeight: int = screenShotHeight // 2

        # Try to create capture using available methods
        camera = create_capture(region)
        if camera is None:
            print("ERROR: Failed to create screen capture using any available method")
            return None, None, None

        print("Starting camera...")
        try:
            # Try BetterCam start method
            if hasattr(camera, 'start'):
                result = camera.start(target_fps=120, video_mode=True)
                if isinstance(result, bool) and not result:
                    print("ERROR: Camera failed to start")
                    return None, None, None
            # Try dxcam start method
            elif hasattr(camera, 'start_capture'):
                camera.start_capture()
            else:
                print("ERROR: Unable to find appropriate method to start capture")
                return None, None, None

            # Verify we can get a frame
            print("Testing frame capture...")
            test_frame = camera.get_latest_frame()
            if test_frame is None:
                print("ERROR: Unable to capture test frame")
                return None, None, None

            print("Camera successfully initialized")
            return camera, cWidth, cHeight

        except Exception as e:
            print(f"ERROR during camera initialization: {str(e)}")
            print("Stack trace:")
            import traceback
            traceback.print_exc()
            return None, None, None

    except Exception as e:
        print(f"ERROR during camera setup: {str(e)}")
        print("Stack trace:")
        import traceback
        traceback.print_exc()
        return None, None, None