"""
Toplevel testbench for a COCOTB testcase
"""

import os
import struct
import random
import logging

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, RisingEdge
from cocotb.drivers.avalon import AvalonSTPkts as AvalonDriver, AvalonMaster
from cocotb.monitors.avalon import AvalonSTPkts as AvalonMonitor
from cocotb.scoreboard import Scoreboard
from cocotb.drivers import BitDriver
from cocotb.regression import TestFactory
from cocotb.result import TestFailure, TestError

# Data generators
from cocotb.generators.bit import wave, intermittent_single_cycles, random_50_percent

from collections import deque

class ETITB(object):

    def __init__(self, dut, debug=True, config_file=None):
        self.dut = dut
        self.log = logging.getLogger("cocotb.eti")

        self.data_in = AvalonDriver(dut, "data_in", dut.clk)
        self.data_out = AvalonMonitor(dut, "data_out", dut.clk)

        level = logging.DEBUG if debug else logging.INFO
        self.log.setLevel(level)
        self.dut.log.setLevel(level)

        self.scoreboard = Scoreboard(dut,fail_immediately=False)


    @cocotb.coroutine
    def initialise(self):
        self.dut.areset_n = 0
        self.dut.data_in_valid = 0
        self.dut.data_out_ready = 1
        yield Timer(12345)
        yield RisingEdge(self.dut.clk)
        self.dut.areset_n = 1
        self.dut.log.info("DUT out of reset")

        for i in xrange(9):
            self.dut.test_status[i] = random.getrandbits(3)
#             self.dut.test_status[i].status0 = random.choice([0,1])
#             self.dut.test_status[i].status1 = random.choice([0,1])
#             self.dut.test_status[i].status2 = random.choice([0,1])

@cocotb.coroutine
def run_test(dut,
            backpressure=False):

    cocotb.fork(Clock(dut.clk, 1000).start())
    tb = ETITB(dut, debug=int(os.getenv('DEBUG')) if os.getenv('DEBUG') else False)

    yield tb.initialise()

    for i in xrange(1000):
        yield RisingEdge(dut.clk)

    raise tb.scoreboard.result



factory = TestFactory(run_test)
factory.generate_tests()

