import torch
import numpy as np
import cv2
import time
import win32api
import win32con
import pandas as pd
import gc
from utils.general import (cv2, non_max_suppression, xyxy2xywh)

# Could be do with
# from config import *
# But we are writing it out for clarity for new devs
from config import aaMovementAmp, useMask, maskWidth, maskHeight, aaQuitKey, screenShotHeight, confidence, headshot_mode, cpsDisplay, visuals, centerOfScreen
import gameSelection

def main():
    # External Function for running the game selection menu (gameSelection.py)
    camera, cWidth, cHeight = gameSelection.gameSelection()

    # Used for forcing garbage collection
    count = 0
    sTime = time.time()

    # Loading Yolo5 Small AI Model, for better results use yolov5m or yolov5l
    model = torch.hub.load('ultralytics/yolov5', 'yolov5s',
                           pretrained=True, force_reload=True)
    stride, names, pt = model.stride, model.names, model.pt

    if torch.cuda.is_available():
        model.half()

    # Used for colors drawn on bounding boxes
    COLORS = np.random.uniform(0, 255, size=(1500, 3))

    # Main loop Quit if Q is pressed
    last_mid_coord = None
    with torch.no_grad():
        while win32api.GetAsyncKeyState(ord(aaQuitKey)) == 0:

            # Getting Frame
            npImg = np.array(camera.get_latest_frame())

            if useMask:
                npImg[-maskHeight:, :maskWidth, :] = 0

            # Normalizing Data
            im = torch.from_numpy(npImg)
            if im.shape[2] == 4:
                # If the image has an alpha channel, remove it
                im = im[:, :, :3,]

            im = torch.movedim(im, 2, 0)
            if torch.cuda.is_available():
                im = im.half()
                im /= 255
            if len(im.shape) == 3:
                im = im[None]

            # Detecting all the objects
            results = model(im, size=screenShotHeight)

            # Suppressing results that dont meet thresholds
            pred = non_max_suppression(
                results, confidence, confidence, 0, False, max_det=1000)

            # Converting output to usable cords
            targets = []
            for i, det in enumerate(pred):
                s = ""
                gn = torch.tensor(im.shape)[[0, 0, 0, 0]]
                if len(det):
                    for c in det[:, -1].unique():
                        n = (det[:, -1] == c).sum()  # detections per class
                        s += f"{n} {names[int(c)]}, "  # add to string

                    for *xyxy, conf, cls in reversed(det):
                        targets.append((xyxy2xywh(torch.tensor(xyxy).view(
                            1, 4)) / gn).view(-1).tolist() + [float(conf)])  # normalized xywh

            targets = pd.DataFrame(
                targets, columns=['current_mid_x', 'current_mid_y', 'width', "height", "confidence"])

            center_screen = [cWidth, cHeight]

            # If there are people in the center bounding box
            if len(targets) > 0:
                if (centerOfScreen):
                    # Compute the distance from the center
                    targets["dist_from_center"] = np.sqrt((targets.current_mid_x - center_screen[0])**2 + (targets.current_mid_y - center_screen[1])**2)

                    # Sort the data frame by distance from center
                    targets = targets.sort_values("dist_from_center")

                # Get the last persons mid coordinate if it exists
                if last_mid_coord:
                    targets['last_mid_x'] = last_mid_coord[0]
                    targets['last_mid_y'] = last_mid_coord[1]
                    # Take distance between current person mid coordinate and last person mid coordinate
                    targets['dist'] = np.linalg.norm(
                        targets.iloc[:, [0, 1]].values - targets.iloc[:, [4, 5]], axis=1)
                    targets.sort_values(by="dist", ascending=False)

                # Take the first person that shows up in the dataframe (Recall that we sort based on Euclidean distance)
                xMid = targets.iloc[0].current_mid_x
                yMid = targets.iloc[0].current_mid_y

                box_height = targets.iloc[0].height
                if headshot_mode:
                    headshot_offset = box_height * 0.38
                else:
                    headshot_offset = box_height * 0.2

                mouseMove = [xMid - cWidth, (yMid - headshot_offset) - cHeight]

                # Moving the mouse
                if win32api.GetKeyState(0x14):
                    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(
                        mouseMove[0] * aaMovementAmp), int(mouseMove[1] * aaMovementAmp), 0, 0)
                last_mid_coord = [xMid, yMid]

            else:
                last_mid_coord = None

            # See what the bot sees
            if visuals:
                # Loops over every item identified and draws a bounding box
                for i in range(0, len(targets)):
                    halfW = round(targets["width"][i] / 2)
                    halfH = round(targets["height"][i] / 2)
                    midX = targets['current_mid_x'][i]
                    midY = targets['current_mid_y'][i]
                    (startX, startY, endX, endY) = int(
                        midX + halfW), int(midY + halfH), int(midX - halfW), int(midY - halfH)

                    idx = 0

                    # draw the bounding box and label on the frame
                    label = "{}: {:.2f}%".format(
                        "Human", targets["confidence"][i] * 100)
                    cv2.rectangle(npImg, (startX, startY), (endX, endY),
                                  COLORS[idx], 2)
                    y = startY - 15 if startY - 15 > 15 else startY + 15
                    cv2.putText(npImg, label, (startX, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS[idx], 2)

            # Forced garbage cleanup every second
            count += 1
            if (time.time() - sTime) > 1:
                if cpsDisplay:
                    print("CPS: {}".format(count))
                count = 0
                sTime = time.time()

                # Uncomment if you keep running into memory issues
                # gc.collect(generation=0)

            # See visually what the Aimbot sees
            if visuals:
                cv2.imshow('Live Feed', npImg)
                if (cv2.waitKey(1) & 0xFF) == ord('q'):
                    exit()
    camera.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exception(e)
        print(str(e))
