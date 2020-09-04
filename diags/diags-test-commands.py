#!/usr/bin/env python3
import logging
import re
import shutil
import subprocess

import util.dmcc_host
from util.dmcc_host import dmcc

IS_LAVA_TEST = False
TEST_NAME_LIST = []

HOST = '127.0.0.1'
PORT = 10026

DEBUG_LEVEL = logging.DEBUG


# list of commands to test
# each entry has 
#   - the commmand name
# each entry can have
#   - args (defaults to None)
#   - a regex to apply to the return value (defaults to None)
#   - a timeout (defaults to None)
commands_to_test = [
    {'command': 'AIMER', 'args': '1 1'},
    {'command': 'AIMER', 'args': '2 1'},
    {'command': 'AIMER', 'args': '1 0'},
    {'command': 'AIMER', 'args': '2 0'},
    {'command': 'DIAGS.VERSION', 'regex': b'v1\.'},
    {'command': 'DOCS', 'regex': b'== Diags 2 =='},
    {'command': 'ECHO', 'args': 'somedata', 'regex': b'somedata'},
    {'command': 'ECHO_DATA', 'args': '9\nsome\ndata', 'regex': b'some\ndata'},
    {'command': 'GPIO.LIST', 'regex': b'Linename'},
    {'command': 'GPIO.READ', 'args': 'BTN_TRIG', 'regex': b'1'},
    # Those lines are unconnected on a DM280 -> safe to test
    {'command': 'GPIO.WRITE', 'args': 'SD2_DATA0 1'},
    {'command': 'GPIO.WRITE', 'args': 'SD2_DATA0 0'},
    {'command': 'HELP', 'regex':b'Diags 2'},
    {'command': 'HELP', 'args': 'HELP', 'regex':b'Add command names'},
    {'command': 'IMAGE.ACQUIRE'},
    {'command': 'IMAGE.FOCUS'},
    {'command': 'IMAGE.RESET'},
    # acquire again after reset as this otherwise breaks transfer commands :O
    {'command': 'IMAGE.ACQUIRE'},
    {'command': 'IMAGE.SAVE_BMP', 'regex': b'.*bmp\n'},
    {'command': 'IMAGE.TFER_8BIT', 'regex': b'\d+\n'},
    {'command': 'IMAGE.TFER_BMP', 'regex': b'\d+\n'},
    {'command': 'IMAGE.TFER_RAW', 'regex': b'\d+\n'},
    {'command': 'M4.LIST_REG', 'regex':b'\[.*\]'},
    {'command': 'M4.READ', 'args': 'sw_version', 'regex':b'0x'},
    {'command': 'M4.WRITE', 'args': 'virtual_input0 1'},
    {'command': 'SLEEP', 'args': '500'},
    {'command': 'SYSTEMDUMP', 'regex': b'\d+\n'},
    {'command': 'TRUE'},
    {'command': 'UBOOT.VERSION', 'regex': b'U-Boot'},
    {'command': 'GET BUTTONS', 'args': 'IO_BOARD_TRIGGER'},
    {'command': 'SET BUZZER.FREQ', 'args': '3000'},
    {'command': 'GET BUZZER.FREQ', 'regex': b'3000'},
    {'command': 'SET BUZZER.FREQ', 'args': '0'},
    {'command': 'GET BUZZER.FREQ', 'regex': b'0'},
    
    
    # move this up to the alphabetical place
    {'command': 'DEVICE.AUTOEXPOSURE', 'timeout':30},
]

# commands we can't properly test here
command_whitelist = [
    # autoload is hard to test
    'AUTOLOAD.RECORD.START',
    'AUTOLOAD.RECORD.STOP',
    'GET AUTOLOAD.DELAY',
    'GET AUTOLOAD.ENABLE',
    'GET AUTOLOAD.LOOP',
    
    # firmware update should be tested seperately
    'FIRMWARE.UPDATE',

    # bad idea :D
    'HALT',
    'REBOOT',
    'POWEROFF',

    # HWDATA should not be touched
    'HWDATA.FORMAT_PARTITION',

    # no loopback
    'LOOPBACK_TEST',

    # no raft
    'RAFT.DELETE',
    'RAFT.DOWNLOAD',
    'RAFT.HOME',
    'RAFT.LIST',
    'RAFT.RESET',
    'RAFT.RESET_HOME',
    'RAFT.ROTATE',
    'RAFT.ROTATE_TO',
    'RAFT.RUN',
    'RAFT.SETTINGS_UPLOAD',
    
    # Only present on Kite
    'USB.ENABLE',
    'WIFI.SCAN',
    'GET BATTERY',
    'OLED.ADD_TEXT',
    'OLED.FILL_RGB',
    'OLED.OPEN_IMAGE',
    'OLED.SEND_IMAGE',
    'OLED.SEND_RAW_IMAGE',
    'BLUETOOTH.SCAN',
    'GET BLUETOOTH.DISCOVERABLE',
    'GET BLUETOOTH.SCAN-RESULTS',
    'GET ACCELEROMETER.DATA',
    'GET CRADLE_DETECT',
    'GET CURRENT-LIMIT',
]

def check_if_lava():
    lava_util = shutil.which('lava-test-case')
    if lava_util:
        global IS_LAVA_TEST
        IS_LAVA_TEST = True


def set_test_name(command_dict):
    """ set command_dict['test_case_name'] to a unique test case name """
    global TEST_NAME_LIST

    if 'args' in command_dict:
        command_str = command_dict['command'] + " " + command_dict['args'] 
    else:
        command_str = command_dict['command']
    lava_test_name = 'test_' + command_str
    lava_test_name = lava_test_name.replace(' ', '_')
    while lava_test_name in TEST_NAME_LIST:
        lava_test_name = lava_test_name + '_again'

    TEST_NAME_LIST.append(lava_test_name)
    command_dict['test_case_name'] = lava_test_name


def report_lava_start(command_dict):
    if IS_LAVA_TEST:
        print("<LAVA_SIGNAL_STARTTC {}>".format(command_dict['test_case_name']))


def report_lava_stop(command_dict):
    if IS_LAVA_TEST:
        print("<LAVA_SIGNAL_ENDTC {}>".format(command_dict['test_case_name']))


def report_lava_result(command_dict, passed = True, measurement = None):
    if IS_LAVA_TEST:
        result = 'pass' if passed else 'fail'
        if measurement is not None:
            measurement_str = "MEASUREMENT={}".format(measurement)
        else:
            measurement_str = ""
        print("<LAVA_SIGNAL_TESTCASE TEST_CASE_ID={} RESULT={} {}>".format(command_dict['test_case_name'],
                result,
                measurement_str))


def discover_commands(connection):
    regular_commands = []
    get_commands = []
    result, retval = connection.send_command_and_check(b"||;1>help")
    if result != b'0':
        raise RuntimeError('Getting the HELP failed with result {}'.format(result))
    for line in retval.decode().splitlines()[2:]:
        command, _help_text = line.split(' - ')
        command = command.strip()
        if 'GET/SET' in command:
            command = command.replace('GET/SET', 'GET')
            get_commands.append(command)
        else:
            regular_commands.append(command)

    return regular_commands, get_commands


def test_command(connection, command_dict):
    if 'args' in command_dict:
        command_str = command_dict['command'] + " " + command_dict['args'] 
    else:
        command_str = command_dict['command']

    if 'timeout' in command_dict:
        bak_timeout = con.timeout
        con.timeout = command_dict['timeout']

    result, retval = con.send_command_and_check("||;1>{}".format(command_str).encode())
    if result != b'0':
        raise RuntimeError("Command {}: returned {}, expected 0".format(command_dict['command'], result))

    if 'timeout' in command_dict:
        con.timeout = bak_timeout

    if 'regex' in command_dict :
        p = re.compile(command_dict['regex'])
        match = p.match(retval)
        if not match:
            raise RuntimeError("Command {}: {} was not matched by {}".format(command_dict['command'], command_dict['regex'], retval))


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logger.setLevel(DEBUG_LEVEL)

    check_if_lava()
    if IS_LAVA_TEST:
        print("LAVA Test, using lava signal")
    else:
        print("Console Test, no use of lava-signals")

    util.dmcc_host.logger.setLevel(logging.DEBUG)
    logger.debug("DMCC connection to %s:%d", HOST, PORT)
    con = dmcc(HOST, PORT, 5)
    
    regular_commands, get_commands = discover_commands(con)

    for command_under_test in commands_to_test:
        set_test_name(command_under_test)
        report_lava_start(command_under_test)
        logger.debug(command_under_test)
        # do the test
        passed = True
        try:
            test_command(con, command_under_test)
        except RuntimeError:
            passed = False

        report_lava_stop(command_under_test)
        report_lava_result(command_under_test, passed)

        # remove from test list
        try:
            if command_under_test['command'].startswith('GET'):
                get_commands.remove(command_under_test['command'])
            else:
                regular_commands.remove(command_under_test['command'])
        except ValueError:
            # we might test a command twice
            pass
        
    # remove whitelisted commands from lists
    for command in command_whitelist:
        if command.startswith('GET'):
            get_commands.remove(command)
        else:
            regular_commands.remove(command)



    if regular_commands:
        logger.warning("%d untested regular commands:", len(regular_commands))
        logger.warning(regular_commands)
    if get_commands:
        logger.warning("%d untested GET/SET commands:", len(get_commands))
        logger.warning(get_commands)