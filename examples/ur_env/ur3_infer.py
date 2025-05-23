import os
os.environ["JAX_TRACEBACK_FILTERING"] = "off"
os.environ["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = ".50"

import sys
sys.path.append('/home/shreya/Desktop/PI/openpi')  # Add the module path
from ur_ikfast import ur_kinematics

import time
import numpy as np
import cv2
from urtde_controller2 import URTDEController, URTDEControllerConfig
from cameras.realsense_camera import RealSenseCamera, get_device_ids
from openpi_client import image_tools
from openpi_client import websocket_client_policy
# Ensure the path is correct based on your project structure
from hardware_env.two_stage import TwoStage
# from ur_ikfast.ur_ikfast import ur_kinematics

# Initialize UR5 and UR3 kinematics
ur5_arm = ur_kinematics.URKinematics('ur5e')
ur3_arm = ur_kinematics.URKinematics('ur3e')

class UR3ControllerWithRemoteInference:
    """Controller for UR3 robot with remote policy server integration."""

    def __init__(self, robot_ip="192.168.77.22", hz=100,  host="localhost", port=8000):
        """Initialize the UR3 controller, cameras, and remote policy client."""
                # Initialize remote policy client
        print(  "Connecting to remote policy server...")
        self.policy_client = websocket_client_policy.WebsocketClientPolicy(host=host, port=port)# Initialize URTDEController
        self.controller_config = URTDEControllerConfig(
            task="two_stage",  # This task is already in the config
            controller_type="CARTESIAN_DELTA",
            max_delta=0.05,
            mock=1,  # Set to 1 for mock mode
            hostname="192.168.77.232",
            robot_port=50002,
            robot_ip=robot_ip,
            hz=hz,
        )

        self.task = TwoStage() 
        # Initialize controller without explicit task parameter (it's already in the config)
        self.controller = URTDEController(self.controller_config,task="two_stage")

        # Initialize RealSense cameras
        device_ids = get_device_ids()
        # Use dummy images for testing
        if not device_ids:
            print("No RealSense cameras found. Using dummy images instead.")
            self.use_dummy_images = True
            self.cameras = {
                "cam0": None,
                "cam1": None,
                "cam2": None
            }
        else:
            print(f"Found {len(device_ids)} cameras: {device_ids}")
            # Initialize cameras (e.g., cam0, cam1, cam2)
            self.cameras = {
                "cam0": RealSenseCamera(device_id=device_ids[0], flip=False),
                "cam1": RealSenseCamera(device_id=device_ids[1], flip=False) if len(device_ids) > 1 else None,
                "cam2": RealSenseCamera(device_id=device_ids[2], flip=False) if len(device_ids) > 2 else None,
            }
            self.use_dummy_images = False

    def capture_images(self):
        """Capture images from all cameras."""
        images = {}
        
        if hasattr(self, 'use_dummy_images') and self.use_dummy_images:
            # Create dummy images with solid colors for testing
            dummy_color = np.zeros((224, 224, 3), dtype=np.uint8)
            
            # Make a simple checkerboard pattern for the dummy image
            for i in range(0, 224, 28):
                for j in range(0, 224, 28):
                    if (i//28 + j//28) % 2 == 0:
                        dummy_color[i:i+28, j:j+28] = [200, 200, 200]  # Light gray
            
            # Add a colored shape in the center to make it more distinctive
            cv2.circle(dummy_color, (112, 112), 50, (0, 0, 255), -1)  # Red circle
            
            # Create a simple depth image (just a gradient)
            dummy_depth = np.zeros((224, 224, 1), dtype=np.uint16)
            for i in range(224):
                dummy_depth[i, :, 0] = i * 20  # Simple gradient
            
            # Add dummy images for all camera positions
            images["cam0"] = {"color": dummy_color, "depth": dummy_depth}
            
            # Make slightly different dummy images for cam1 and cam2
            cam1_color = dummy_color.copy()
            cv2.rectangle(cam1_color, (84, 84), (140, 140), (0, 255, 0), -1)  # Green square
            images["cam1"] = {"color": cam1_color, "depth": dummy_depth}
            
            return images
        
        # Regular camera capture for real cameras
        for name, camera in self.cameras.items():
            if camera is not None:
                color_image, depth_image = camera.read()
                images[name] = {
                    # "color": image_tools.convert_to_uint8(
                    #     image_tools.resize_with_pad(color_image, 224, 224)
                    # ),
                    "color": cv2.resize(color_image, (224, 224)),
                    "depth": depth_image,
                }
        
        return images
    
    def get_robot_state(self):
        """Retrieve the current state of the robot."""
        # The get_state() method returns a tuple (state, in_good_range)
        state_tuple = self.controller.get_state()
        print(f"Robot state tuple: {state_tuple}")
        
        # Unpack the tuple to get just the state dictionary
        state_dict, in_good_range = state_tuple
        print(f"Robot state dict: {state_dict}, in_good_range: {in_good_range}")
        
        # Now you can access the joint_positions and gripper_position keys
        joint_positions = state_dict["joint_positions"]
        gripper_position = state_dict["robot0_gripper_qpos"]
        
        # Convert to numpy arrays if necessary
        if isinstance(joint_positions, list):
            joint_positions = np.array(joint_positions)
        if isinstance(gripper_position, list):
            gripper_position = np.array(gripper_position)
        
        # Create a new state dictionary with just the keys you need
        result_state = {
            "joint_positions": joint_positions,
            "gripper_position": gripper_position
        }
        
        return result_state
    

    def query_policy_server(self, prompt, images, state):
        """Query the remote policy server for actions."""
        # Construct the observation in UR5 format
        observation = {
            "joints": state["joint_positions"],  # Joint positions
            "gripper": state["gripper_position"],  # Gripper position
            "base_rgb": images.get("cam0", {}).get("color", None),  # Base camera
            "wrist_rgb": images.get("cam1", {}).get("color", None),  # Wrist camera
            "prompt": prompt,  # Language prompt
        }
        
        cv2.imwrite("base_rgb.png", observation["base_rgb"])
        cv2.imwrite("wrist_rgb.png", observation["wrist_rgb"])

        print(f"Sending observation: {observation}")
        
        # Query the policy server
        result = self.policy_client.infer(observation)
        return result["actions"]
        
    def execute_action(self, action):
        """Send the action to the robot."""
        
        # Convert from [-1,1] range to the actual delta range
        pos_scaling = np.array([0.01, 0.01, 0.01, 0.05, 0.05, 0.05, 1.0])
        
        # Adjust the normalization if your policy outputs in a different range
        normalized_action = np.clip(action, -1.0, 1.0)
        
        # Scale to the actual control range
        scaled_action = normalized_action * pos_scaling

        # Handle gripper specially (it's typically [0,1] not [-1,1])
        if len(scaled_action) == 7:
            scaled_action[6] = (normalized_action[6] + 1) / 2.0  # Map from [-1,1] to [0,1]

        gripper_position = scaled_action[6]
        scaled_action = scaled_action[:6]  # Remove gripper position for IK calculation
        
        ur5_pose_quat = ur5_arm.forward(scaled_action)
        ur5_pose_matrix = ur5_arm.forward(scaled_action, 'matrix')
        print("UR5 Pose:", ur5_pose_quat)

        # Adjust the initial guess to be closer to the expected solution
        ur3_joint_angles = ur3_arm.inverse(ur5_pose_quat, False, q_guess=scaled_action)  # Use scaled_action as initial guess
        print("UR3 Joint Angles (IK):", ur3_joint_angles)

        # Validate joint angles (example validation)
        if any(angle < -np.pi or angle > np.pi for angle in ur3_joint_angles):
            print("Invalid joint angles. Skipping execution.")
            return
        # add back the gripper pos
        if len(ur3_joint_angles) == 7:
            ur3_joint_angles[6] = scaled_action[6]  # Gripper position
        else:     
            ur3_joint_angles_with_gripper = np.append(ur3_joint_angles, gripper_position) # Add gripper position
 
        self.controller.update_joint(ur3_joint_angles_with_gripper)

        print(f"Executing action: {ur3_joint_angles_with_gripper}")


        
    def reset(self):
        """Reset the robot to the home position."""
        self.controller.reset()

    def cleanup(self):
        """Clean up resources."""
        self.controller.reset()
        if not hasattr(self, 'use_dummy_images') or not self.use_dummy_images:
                for camera in self.cameras.values():
                    if camera is not None:
                        camera._pipeline.stop()


def main():
    """Main function to run the UR3 controller with remote policy server integration."""
    prompt = "Press the red button"
    robot_ip = "192.168.77.22"
    host = "localhost"  # Replace with the policy server's IP address
    port = 8000

    # Initialize the controller without the task parameter
    controller = UR3ControllerWithRemoteInference(
        robot_ip=robot_ip,
        host=host, 
        port=port
    )

    try:
        # Reset the robot
        controller.reset()

        # Run inference and execute actions
        for step in range(5):  # Run for 10 steps
            print(f"Step {step + 1}")

            # Capture images
            images = controller.capture_images()

            # Get robot state
            state = controller.get_robot_state()

            # Query the policy server
            action_chunk = controller.query_policy_server(prompt, images, state)
            print(f"Received action chunk: {action_chunk}")

            # Execute the first action in the action chunk
            controller.execute_action(action_chunk[0])

            time.sleep(0.1)  # Control loop delay

    except KeyboardInterrupt:
        print("Interrupted by user. Stopping...")

    finally:
        # Clean up resources
        controller.cleanup()


if __name__ == "__main__":
    main()