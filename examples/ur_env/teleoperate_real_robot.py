import numpy as np
import time
from urtde_controller2 import URTDEController, URTDEControllerConfig
from pynput import keyboard
from hardware_env.save_csv import save_frame
import datetime
from pathlib import Path
from hardware_env.ur3e_utils import Rate


def save_start_status(status, filename="start_status.txt"):
    with open(filename, "w") as f:
        f.write(status)



# Initial step size for each command
STEP_SIZE = 0.005
current_position = [0, 0, 0, 0, 0, 0, 0.0]  # Assuming initial position with 0 deltas and gripper open

def on_press(key):
    global current_position
    try:
        if key.char == 'a':
            print("w pressed")
            current_position[0] -= STEP_SIZE
        elif key.char == 'd':
            print("s pressed")
            current_position[0] += STEP_SIZE
        elif key.char == 's':
            print("a pressed")
            current_position[1] -= STEP_SIZE
        elif key.char == 'w':
            print("d pressed")
            current_position[1] += STEP_SIZE
        elif key.char == 'r':
            print("r pressed")
            current_position[-1] = 0.8
        elif key.char == 'e':
            print("e pressed")
            current_position[-1] = 0.0
        elif key.char == 'q':
            print("q pressed")
            current_position = [0, 0, 0, 0, 0, 0, current_position[-1]]
    except AttributeError:
        if key == keyboard.Key.up:
            print("up pressed")
            current_position[2] += STEP_SIZE
        elif key == keyboard.Key.down:
            print("down pressed")
            current_position[2] -= STEP_SIZE
        elif key == keyboard.Key.esc:
            save_start_status("Stopped")
            print("esc pressed")
            return False  # Stop listener

def teleoperation():
    cfg = URTDEControllerConfig(
        task="two_stage",
        controller_type="CARTESIAN_DELTA",
        max_delta=0.06,
        mock=0,
        hostname="192.168.77.134",
        robot_port=50002,
        robot_ip="192.168.77.22",
        hz=100
    )
    
    controller = URTDEController(cfg, task=cfg.task)
    time.sleep(5)

    # Set start_status.txt to started

    # Keyboard Listener
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    save_start_status("Reached Start")

    # Set paths and file names
    csv_file_name = f"{datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.csv"
    save_path = Path("data").expanduser()

    print("Teleoperation started. Use 'w', 'a', 's', 'd', 'up', 'down' keys to control the robot. Press 'esc' to stop.")
    
    # # generate random start position
    # start_position = np.random.uniform(-0.05, 0.05, 2)
    # random_start = [0, 0, 0, 0, 0, 0, 1.0]
    # random_start[0] = start_position[0]
    # random_start[1] = start_position[1]
    # print(f"Random start position: {random_start}")
    # controller.update(np.array(random_start))

    while listener.running:
        try:
            controller.update(np.array(current_position))

            # Save robot state to CSV
            obs, _ = controller.get_state()
            joint_states = obs['joint_positions']
            ee_pos_quat = np.concatenate((obs['robot0_eef_pos'], obs['robot0_eef_quat']))
            dt = datetime.datetime.now()
            print(ee_pos_quat)
            with Rate(19):
                save_frame(save_path, dt, joint_states, ee_pos_quat, csv_file_name)


        except KeyboardInterrupt:
            save_start_status("Stopped")
            print("\nExiting...")

if __name__ == "__main__":
    teleoperation()
