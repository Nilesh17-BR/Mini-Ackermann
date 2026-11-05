from setuptools import find_packages, setup

package_name = 'four_motor_ctrl'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/scripts', ['scripts/setup_serial_permissions.sh']),
        ('share/' + package_name + '/udev', ['udev/99-four-motor-serial.rules']),
    ],
    install_requires=['setuptools', 'pyserial>=3.5,<4'],
    zip_safe=True,
    maintainer='nilesh',
    maintainer_email='nilesh@example.com',
    description='Four-wheel ROS 2 velocity to STM32 serial DAC bridge.',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'ros_serial_dac = four_motor_ctrl.ros_serial_dac:main',
        ],
    },
)
