from typing import Dict

import numpy as np

from robots.robot import Robot

# import torch

from hardware_env.ur3e_utils import Rate
from scipy.spatial.transform import Rotation


class URRobot(Robot):
    """A class representing a UR robot."""

    def __init__(self, robot_ip: str = "192.168.1.10", control_rate_hz: float = 100.0, no_gripper: bool = False):
        import rtde_control
        import rtde_receive

        [print("in ur robot") for _ in range(4)]
        try:
            self.robot = rtde_control.RTDEControlInterface(robot_ip)
        except Exception as e:
            print(e)
            print(robot_ip)

        control_rate_hz: float = 100.0

        hz = 15
        self.r_inter = rtde_receive.RTDEReceiveInterface(robot_ip, hz)
        if not no_gripper:
            from robots.robotiq_gripper import RobotiqGripper

            self.gripper = RobotiqGripper()
            self.gripper.connect(hostname=robot_ip, port=63352)
            print("gripper connected")
            # gripper.activate()

        [print("connect") for _ in range(4)]

        self._free_drive = False
        self.robot.endFreedriveMode()
        self._use_gripper = not no_gripper
        # self.rate = Rate(control_rate_hz)

    def num_dofs(self) -> int:
        """Get the number of joints of the robot.

        Returns:
            int: The number of joints of the robot.
        """
        if self._use_gripper:
            return 7
        return 6

     
    def _get_gripper_pos(self) -> float:
        import time

        # time.sleep(0.01)
        gripper_pos = self.gripper.get_current_position()
        assert 0 <= gripper_pos <= 255, "Gripper position must be between 0 and 255"
        return gripper_pos / 255

    def get_joint_state(self) -> np.ndarray:
        """Get the current state of the leader robot.

        Returns:
            T: The current state of the leader robot.
        """
        robot_joints = self.r_inter.getActualQ()
        if self._use_gripper:
            gripper_pos = self._get_gripper_pos()
            pos = np.append(robot_joints, gripper_pos)
        else:
            pos = robot_joints
        return pos
        

    def get_ee_pose(self) -> np.ndarray:
        """
        Gives out the end effector position of the leader robot.
        """

        robot_end_eff_pos = self.r_inter.getActualTCPPose()
        # Convert r_vec to rpy angles
        # rpy = Rotation.from_rotvec(robot_end_eff_pos[3:]).as_euler("xyz")
        # robot_end_eff_pos = np.append(robot_end_eff_pos[:3], rpy)
        if self._use_gripper:
            gripper_pos = self._get_gripper_pos()
            end_eff_pos = np.append(robot_end_eff_pos, gripper_pos)
            # end_eff_pos = robot_end_eff_pos
            # end_eff_quat = robot_end_eff_pos[3:]
        else:
            end_eff_pos = robot_end_eff_pos
            # end_eff_quat = robot_end_eff_pos[3:]
        return end_eff_pos

    def command_joint_state(self, joint_state: np.ndarray) -> None:
        """Command the leader robot to a given state.

        Args:
            joint_state (np.ndarray): The state to command the leader robot to.
        """
        velocity = 0.1
        acceleration = 0.1
        # dt = 1.0 / 500  # 2ms
        dt = 1.0
        lookahead_time = 0.2
        gain = 100

        robot_joints = joint_state[:6]

        print("robot_joints", robot_joints) 
        t_start = self.robot.initPeriod()
        success = self.robot.servoJ(
            robot_joints, velocity, acceleration, dt, lookahead_time, gain
        )
        print("success", success)
        if self._use_gripper:
            gripper_pos = joint_state[-1] * 255
            self.gripper.move(gripper_pos, 255, 10)
        self.robot.waitPeriod(t_start)

    def command_eef_pose(self, eef_pos: np.ndarray) -> None:
        """Command the leader robot to a given eef_pose.

        Args:
            eef_pose (np.ndarray): The eef_pose to command the leader robot to.
        """
        if self._use_gripper:
            gripper_qpos = eef_pos[-1] * 255
            eef_pos = eef_pos[:-1].tolist()
        velocity = 0.1
        acceleration = 0.1
        # dt = 1.0 / 500  # 2ms
        dt = 0.0002
        lookahead_time = 0.2
        gain = 100

        t_start = self.robot.initPeriod()

        # print("Entered command_eef_pose")
        try:
            self.robot.servoL(eef_pos, velocity, acceleration, dt, lookahead_time, gain)
            # self.robot.moveL(eef_pos, speed=0.1, acceleration=0.1)
            if self._use_gripper:
                # gripper_pos = eef_pos[-1] * 255
                self.gripper.move(gripper_qpos, 255, 10)
        except Exception as e:
            print(f"Error in command_eef_pose: {e}")
        self.robot.waitPeriod(t_start)
    
    def freedrive_enabled(self) -> bool:
        """Check if the robot is in freedrive mode.

        Returns:
            bool: True if the robot is in freedrive mode, False otherwise.
        """
        return self._free_drive

    def set_freedrive_mode(self, enable: bool) -> None:
        """Set the freedrive mode of the robot.

        Args:
            enable (bool): True to enable freedrive mode, False to disable it.
        """
        if enable and not self._free_drive:
            self._free_drive = True
            self.robot.freedriveMode()
        elif not enable and self._free_drive:
            self._free_drive = False
            self.robot.endFreedriveMode()


def main():
    robot_ip = "192.168.1.11"
    ur = URRobot(robot_ip, no_gripper=True)
    print(ur)
    ur.set_freedrive_mode(True)
    print(ur.get_observations())


if __name__ == "__main__":
    main()
