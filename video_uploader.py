import datetime
import os
import paramiko
import time
from getpass import getpass
from moviepy import VideoFileClip
from socket import gaierror, error
from stat import S_ISDIR # For checking if remote path is a directory

# --- Configuration ---
confirm = ['true', '1', 't', 'y', 'yes', 'yeah', 'yup', 'certainly', 'uh-huh']
HIDDEN_INPUT = input('Do you want to input all server credentials hidden (No): ').strip().lower() in confirm
LOCAL_CLIPS_DIRECTORY = input('Enter path to clips directory (clips): ').strip() or "clips"

if HIDDEN_INPUT:
    SERVER_HOST = getpass('Enter server host IP or URL: ').strip()
    SERVER_PORT = int(getpass('Enter server port (22): ').strip() or "22") # Standard SSH/SFTP port
    SERVER_USER = getpass('Enter server user: ').strip()
else:
    SERVER_HOST = input('Enter server host IP or URL: ').strip()
    SERVER_PORT = int(input('Enter server port (22): ').strip() or "22") # Standard SSH/SFTP port
    SERVER_USER = input('Enter server user: ').strip()
    
SERVER_PASSWORD = getpass('Enter password of user (input is hidden): ').strip() # Or use SSH keys for better security
REMOTE_BASE_DIRECTORY = input('Enter path to server clips directory (/): ').strip() or "/" # Base directory on the server
TARGET_FILE_LENGTH_SECONDS = int(input('Min video duration in seconds (60): ').strip() or "60") # 1 minute
ONLY_TODAY_CLIPS = input('Only upload clips from today (No): ').strip().lower() in confirm

def create_sftp_client(host, port, user, password=None, key_filename=None):
    """Creates and returns an SFTPClient object."""
    try:
        transport = paramiko.Transport((host, port))
    except Exception as e:
        print(f"An unexpected error occurred during SFTP transport: {e}")
        return None, None
    
    try:
        if key_filename:
            # For key-based authentication
            key = paramiko.RSAKey.from_private_key_file(key_filename) # Or DSSKey, ECDSAKey, EdDSAKey
            transport.connect(username=user, pkey=key)
        else:
            # For password-based authentication
            transport.connect(username=user, password=password)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        print(f"SFTP connection to {host} established successfully.")
        return sftp, transport # Return both sftp client and transport for proper closing
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check username and password/key.")
        if transport.is_active():
            transport.close()
        return None, None
    except paramiko.SSHException as e:
        print(f"Could not establish SFTP connection: {e}")
        if transport.is_active():
            transport.close()
        return None, None
    except gaierror as e:
        print(f"A socket.gaierror error occurred: {e}")
        if transport.is_active():
            transport.close()
        return None, None
    except OSError as e:
        print(f"An OSError occurred: {e}")
        if transport.is_active():
            transport.close()
        return None, None
    except TimeoutError as e:
        print(f"A TimeoutError occurred: {e}")
        if transport.is_active():
            transport.close()
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred during SFTP connection: {e}")
        if transport.is_active():
            transport.close()
        return None, None

def get_file_duration(filepath):
    try:
        clip = VideoFileClip(filepath)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        print(f"Fehler mit moviepy beim Ermitteln der Dauer von {filepath}: {e}")
        return None

def remote_directory_exists(sftp_client, remote_path):
    """Checks if a directory exists on the remote server using SFTP."""
    try:
        stat_info = sftp_client.stat(remote_path)
        return S_ISDIR(stat_info.st_mode)
    except error as e:
        print(f"socket.error was raised: {e}")
        return False
    except gaierror as e:
        print(f"socket.gaierror was raised: {e}")
        return False
    except IOError as e:
        # If the path does not exist, stat will raise an IOError (FileNotFoundError is a subclass)
        # Check specific error code if needed, but for "does it exist?" checking IOError is often enough.
        if "No such file" in str(e): # Common error message for non-existent path
            return False
        raise # Re-raise other IOErrors
    except OSError as e:
        print(f"An OSError occurred: {e}")
        return False
    except paramiko.SSHException as e:
        print(f"A SSHException occurred: {e}")
        return False
    except Exception as e:
        print(f"Error checking remote directory existence '{remote_path}': {e}")
        return False

def remote_file_exists(sftp_client, remote_path):
    """Checks if a file exists on the remote server using SFTP."""
    try:
        sftp_client.stat(remote_path)
        return True
    except error as e:
        print(f"socket.error was raised: {e}")
        return False
    except gaierror as e:
        print(f"socket.gaierror was raised: {e}")
        return False
    except IOError as e:
        if "No such file" in str(e):
            return False
        raise # Re-raise other IOErrors
    except OSError as e:
        print(f"An OSError occurred: {e}")
        return False
    except paramiko.SSHException as e:
        print(f"A SSHException occurred: {e}")
        return False
    except Exception as e:
        print(f"Error checking remote file existence '{remote_path}': {e}")
        return False

def main():
    if not os.path.exists(LOCAL_CLIPS_DIRECTORY):
        print(f"Error: Local directory '{LOCAL_CLIPS_DIRECTORY}' does not exist.")
        return

    # Establish SFTP connection
    sftp_client, transport = create_sftp_client(SERVER_HOST, SERVER_PORT, SERVER_USER, SERVER_PASSWORD)
    if not sftp_client:
        return

    try:
        # Current date for the remote directory
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        remote_upload_directory = os.path.join(REMOTE_BASE_DIRECTORY, today_str).replace("\\", "/") # For Linux paths

        # Check and create daily directory on the server
        if not remote_directory_exists(sftp_client, remote_upload_directory):
            try:
                # SFTP mkdir can only create one level at a time.
                # We need to ensure the parent directory (REMOTE_BASE_DIRECTORY) exists,
                # then create the daily directory.
                # For this script, we assume REMOTE_BASE_DIRECTORY already exists.
                # If not, you'd need a recursive mkdir function.
                sftp_client.mkdir(remote_upload_directory)
                print(f"Remote directory '{remote_upload_directory}' for today created.")
            except IOError as e:
                print(f"Error creating remote directory '{remote_upload_directory}': {e}")
                print("Make sure the parent directory (REMOTE_BASE_DIRECTORY) exists and you have permissions.")
                sftp_client.close()
                transport.close()
                return
            except Exception as e:
                print(f"An Exception occurred: {e}")
                return
        else:
            print(f"Remote directory '{remote_upload_directory}' already exists.")

        # Scan the local directory for MP4 files
        for filename in os.listdir(LOCAL_CLIPS_DIRECTORY):
            if filename.endswith(".mp4"):
                local_filepath = os.path.join(LOCAL_CLIPS_DIRECTORY, filename)
                remote_filepath = os.path.join(remote_upload_directory, filename).replace("\\", "/")

                print(f"\nProcessing file: {local_filepath}")
                
                # Check if the file is not from today
                if ONLY_TODAY_CLIPS and not today_str in filename:
                    print(f"File '{filename}' is not from today ({today_str}). Skipping.")
                    continue

                # Check if the file already exists on the server
                if remote_file_exists(sftp_client, remote_filepath):
                    print(f"File '{filename}' already exists on the server. Skipping.")
                    continue

                # Determine the duration of the MP4 file
                duration = get_file_duration(local_filepath)

                if duration is not None:
                    # Check if the duration matches the target (with some tolerance)
                    if abs(duration - TARGET_FILE_LENGTH_SECONDS) < 5: # 5 seconds tolerance
                        print(f"Uploading '{filename}' (Duration: {duration:.2f}s)...")
                        try:
                            sftp_client.put(local_filepath, remote_filepath)
                            print(f"'{filename}' uploaded successfully to '{remote_filepath}'.")
                        except Exception as e:
                            print(f"Error uploading '{filename}': {e}")
                    else:
                        print(f"'{filename}' does not have the desired length of {TARGET_FILE_LENGTH_SECONDS} seconds (is: {duration:.2f}s). Skipping.")
                else:
                    print(f"Could not determine duration for '{filename}'. Skipping.")

    finally:
        if sftp_client:
            sftp_client.close()
        if transport and transport.is_active():
            transport.close()
        print("\nSFTP connection closed.")

if __name__ == "__main__":
    sleep_seconds = 300
    while True:
        print("\n----- Start Loop -----")
        main()
        print(f"----- Pause Loop for {sleep_seconds} seconds -----\n")
        time.sleep(sleep_seconds)