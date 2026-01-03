# Surveillance Camera
Python script to record and upload clips from a webcam.

## Install dependencies
````bash
pip install paramiko moviepy opencv-python pillow
````
or
````bash
sudo apt-get install python3-paramiko python3-moviepy python3-opencv python3-pil python3-pil.imagetk
````

## Execute
- `python webcam_recorder.py` for the Webcam Recorder GUI
- `python clip_uploader.py` for uploading clips to a remote server via SFTP

Tested on Win11 and [Raspbian Pi OS](https://www.raspberrypi.com/software/operating-systems/)

## Webcam Recorder
By clicking **Start Recording**, the Webcam Recorder saves every 60 seconds a clip, in the defined clips directory.
The recorder saves only the latest 10 clips. Older clips will be removed.

## Upload Clips
Uploads clips to a remote server via SFTP.
Creates diroctories on server in the format of `YYYY-MM-DD` for each day.
