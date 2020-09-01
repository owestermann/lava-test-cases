# -*- coding: utf-8 -*-
"""
Created on May 30, 2018

@author: oliver.westermann@cognex.com
"""

import logging
import socket
import re
import time


logger = logging.getLogger(__name__)

class dmcc():
    """
    class to connect to a device running diags and send commands

    provides the necessary parsers for communication as well as
    statistics for tests
    """

    def __init__(self, host, port, timeout):
        self.timeout = timeout
        self.start_time = int(round(time.time() * 1000))

        self.print_ts("Initializing DMCC connection to {}:{}".format(host, port))
        self.tmp_buf = bytearray()
        self.tmp_buf_part = ""
        self.ts_tmp_buf_part = ""
        self.last_cmd = ""
        self.error_buf = ""
        self.ts_last_cmd = None
        self.success_count = 0
        self.failure_count = 0
        self.slowest_cmd = None
        self.slowest_cmd_time = 0
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection.settimeout(timeout)
        self.connection.connect((host, port))
        self.connection.setblocking(False)
        result = b"\[(\d*)\]\r?\n"  # [something in the form of "[0]\n" or "[102]\n"
        additional_return_data = b"((.*\n?)*)"
        self.re_result = re.compile(result + additional_return_data)

    def _write(self, data):
        self.connection.sendall(data)

    def reset(self):
        """
        reset the fail/pass/timing statistics
        """
        self.start_time = int(round(time.time() * 1000))
        self.success_count = 0
        self.failure_count = 0
        self.slowest_cmd = None
        self.slowest_cmd_time = 0
        self.error_buf = ""
        self.print_ts("DMCC stats reset")

    def print_ts(self, args):
        """
        print a string with a leading timestamp
        """
        time_passed = int(round(time.time() * 1000)) - self.start_time
        line = "{:<6}: {}".format(time_passed, args)
        logger.debug(line)

    def dmcc_write(self, data):
        """
        send data (a bytes/bytearray object) to device
        """
        send_str = data + b'\r\n'
        self.last_cmd = data
        self.tmp_buf = bytearray()
        self.ts_last_cmd = time.time()
        return self._write(send_str)

    def dmcc_read(self, timeout):
        """
        read command and try to seperate between return code and data

        The command waits up to timeout seconds to get a result. A result
        consists at least of "[<return code]\n", but can be followed by
        additional data.
        If it gets more data within 0.1s, it will continue to read until
        it hasn't got any data for 0.1s
        """
        new_data_timeout = 0.1
        starting_time = time.time()
        last_data = starting_time
        continue_reading = True
        while(continue_reading):
            new_data = None
            try:
                new_data = self.connection.recv(512)
            except BlockingIOError:
                pass

            if new_data:
                self.tmp_buf.extend(new_data)
                last_data = time.time()

            if self.re_result.search(self.tmp_buf[:15]):
                # a return code in the first 15 chars
                if time.time() - last_data > new_data_timeout:
                    # and no new data
                    logging.info("Stopped because of {}s timeout".format(new_data_timeout))
                    continue_reading = False
            elif(time.time() > starting_time + timeout):
                logger.debug("No result within {}s".format(timeout))
                continue_reading = False

        command = self.last_cmd
        if last_data:
            time_taken = last_data - self.ts_last_cmd
        else:
            time_taken = -1
        match = self.re_result.search(self.tmp_buf)
        if match:
            result = match.group(1)
            return_val = match.group(2)
            self.tmp_buf = bytearray()
            if time_taken > self.slowest_cmd_time:
                self.slowest_cmd_time = time_taken
                self.slowest_cmd = self.last_cmd
            if result == b"0":
                self.success_count = self.success_count + 1

                self.print_ts("{} succeeded with result {} in {}ms, retval[0:50]: \r\n{}".format(command, result, time_taken * 1000, repr(return_val[0:50])))
            else:
                self.failure_count = self.failure_count + 1
                failure_msg = "{} failed with result {} in {}ms, retval[0:50]: \r\n{}".format(command, result, time_taken * 1000, repr(return_val[0:50]))
                self.error_buf = self.error_buf + failure_msg
                self.print_ts(failure_msg)
            return result, return_val
        else:
            self.failure_count = self.failure_count + 1
            failure_msg = "{} failed after {}ms, buffer[0:50]: \r\n{}".format(command, time_taken * 1000, repr(self.tmp_buf[0:50]))
            self.error_buf = self.error_buf + failure_msg
            self.print_ts(failure_msg)
            self.tmp_buf = bytearray()
            return None, None

    def send_command_and_check(self, command):
        """
        send a command and check response
        """
        self.tmp_buf = bytearray()
        self.print_ts("sending {}".format(command))
        self.dmcc_write(command)
        return self.dmcc_read(self.timeout)

    def final(self):
        """
        print statistics including passed/failed commands
        """
        self.print_ts('-' * 80)
        self.print_ts("Finished with {} succeeded and {} failed commands".format(self.success_count, self.failure_count))
        self.print_ts("Error Buf:\r\n{}".format(self.error_buf))
        self.print_ts("Slowest command {} took {}ms".format(self.slowest_cmd, self.slowest_cmd_time * 1000))
