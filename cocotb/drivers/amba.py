''' Copyright (c) 2014 Potential Ventures Ltd
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of Potential Ventures Ltd,
      SolarFlare Communications Inc nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL POTENTIAL VENTURES LTD BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. '''
"""
Drivers for Advanced Microcontroller Bus Architecture
"""
import cocotb
from cocotb.triggers import RisingEdge, ReadOnly, Lock
from cocotb.drivers import BusDriver
from cocotb.result import ReturnValue
from cocotb.binary import BinaryValue

import binascii
import array


class AXIProtocolError(Exception):
    pass


class AXI4LiteMaster(BusDriver):
    """
    AXI4-Lite Master

    TODO: Kill all pending transactions if reset is asserted...
    """
    _signals = ["AWVALID", "AWADDR", "AWREADY",        # Write address channel
                "WVALID", "WREADY", "WDATA", "WSTRB",  # Write data channel
                "BVALID", "BREADY", "BRESP",           # Write response channel
                "ARVALID", "ARADDR", "ARREADY",        # Read address channel
                "RVALID", "RREADY", "RRESP", "RDATA"]  # Read data channel

    _default_config = {
        "address_latency" : 0,
        "data_latency" : 0,
    }

    def __init__(self, entity, name, clock, **kwargs):
        BusDriver.__init__(self, entity, name, clock)

        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self.bus.AWVALID.setimmediatevalue(0)
        self.bus.WVALID.setimmediatevalue(0)
        self.bus.ARVALID.setimmediatevalue(0)
        self.bus.BREADY.setimmediatevalue(1)
        self.bus.RREADY.setimmediatevalue(1)

        # Mutex for each channel that we master to prevent contention
        self.write_address_busy = Lock("%s_wabusy" % name)
        self.read_address_busy = Lock("%s_rabusy" % name)
        self.write_data_busy = Lock("%s_wbusy" % name)

        config = kwargs.pop('config', {})
        self.config = AXI4LiteMaster._default_config.copy()

        for configoption, value in config.items():
            self.config[configoption] = value
            self.log.debug("Setting config option %s to %s" %
                           (configoption, str(value)))
    @cocotb.coroutine
    def _send_write_address(self, address, delay=0):
        """
        Send the write address, with optional delay (in clocks)
        """
        yield self.write_address_busy.acquire()
        for cycle in range(max(self.config["address_latency"], delay)):
            yield RisingEdge(self.clock)

        self.bus.AWADDR <= address
        self.bus.AWVALID <= 1

        while True:
            yield ReadOnly()
            if self.bus.AWREADY.value:
                break
            yield RisingEdge(self.clock)
        yield RisingEdge(self.clock)
        self.bus.AWVALID <= 0
        self.write_address_busy.release()

    @cocotb.coroutine
    def _send_write_data(self, data, delay=0, byte_enable=0xF):
        """
        Send the write address, with optional delay (in clocks)
        """
        yield self.write_data_busy.acquire()
        for cycle in range(max(self.config["data_latency"], delay)):
            yield RisingEdge(self.clock)

        self.bus.WDATA <= data
        self.bus.WVALID <= 1
        self.bus.WSTRB <= byte_enable

        while True:
            yield ReadOnly()
            if self.bus.WREADY.value:
                break
            yield RisingEdge(self.clock)
        yield RisingEdge(self.clock)
        self.bus.WVALID <= 0
        self.write_data_busy.release()

    @cocotb.coroutine
    def write(self, address, value, byte_enable=0xf, address_latency=0,
              data_latency=0, sync=True):
        """
        Write a value to an address.

        Args:
            address (int): The address to write to
            value (int): The data value to write
            byte_enable (int, optional): Which bytes in value to actually write.
                Default is to write all bytes.
            address_latency (int, optional): Delay before setting the address (in clock cycles).
                Default is no delay.
            data_latency (int, optional): Delay before setting the data value (in clock cycles).
                Default is no delay.
            sync (bool, optional): Wait for rising edge on clock initially.
                Defaults to True.
            
        Returns:
            BinaryValue: The write response value
            
        Raises:
            AXIProtocolError: If write response from AXI is not ``OKAY``
        """
        if sync:
            yield RisingEdge(self.clock)

        c_addr = cocotb.fork(self._send_write_address(address,
                                                      delay=address_latency))
        c_data = cocotb.fork(self._send_write_data(value,
                                                   byte_enable=byte_enable,
                                                   delay=data_latency))

        if c_addr:
            yield c_addr.join()
        if c_data:
            yield c_data.join()

        # Wait for the response
        while True:
            yield ReadOnly()
            if self.bus.BVALID.value and self.bus.BREADY.value:
                result = self.bus.BRESP.value
                self.log.debug("Writing to address 0x%08x with 0x%08x" %
                               (address, value))
                break
            yield RisingEdge(self.clock)

        yield RisingEdge(self.clock)

        if int(result):
            raise AXIProtocolError("Write to address 0x%08x failed with BRESP: %d"
                               % (address, int(result)))

        raise ReturnValue(result)

    @cocotb.coroutine
    def read(self, address, sync=True):
        """
        Read from an address.
        
        Args:
            address (int): The address to read from
            sync (bool, optional): Wait for rising edge on clock initially.
                Defaults to True.
            
        Returns:
            BinaryValue: The read data value
            
        Raises:
            AXIProtocolError: If read response from AXI is not ``OKAY``
        """
        if sync:
            yield RisingEdge(self.clock)

        self.bus.ARADDR <= address
        self.bus.ARVALID <= 1

        while True:
            yield ReadOnly()
            if self.bus.ARREADY.value:
                break
            yield RisingEdge(self.clock)

        yield RisingEdge(self.clock)
        self.bus.ARVALID <= 0

        while True:
            yield ReadOnly()
            if self.bus.RVALID.value and self.bus.RREADY.value:
                data = self.bus.RDATA.value
                result = self.bus.RRESP.value
                self.log.debug("Data at address 0x%08x is 0x%08x" %
                               (address, data))
                break
            yield RisingEdge(self.clock)

        if int(result):
            raise AXIProtocolError("Read address 0x%08x failed with RRESP: %d" %
                               (address, int(result)))

        raise ReturnValue(data)

    def __len__(self):
        return 2**len(self.bus.ARADDR)

class AXI4Slave(BusDriver):
    '''
    AXI4 Slave

    Monitors an internal memory and handles read and write requests.
    '''
    _signals = [
        "ARREADY", "ARVALID", "ARADDR",             # Read address channel
        "ARLEN",   "ARSIZE",  "ARBURST", "ARPROT",

        "RREADY",  "RVALID",  "RDATA",   "RLAST",   # Read response channel

        "AWREADY", "AWADDR",  "AWVALID",            # Write address channel
        "AWPROT",  "AWSIZE",  "AWBURST", "AWLEN",

        "WREADY",  "WVALID",  "WDATA",

    ]

    # Not currently supported by this driver
    _optional_signals = [
        "WLAST",   "WSTRB",
        "BVALID",  "BREADY",  "BRESP",   "RRESP",
        "RCOUNT",  "WCOUNT",  "RACOUNT", "WACOUNT",
        "ARLOCK",  "AWLOCK",  "ARCACHE", "AWCACHE",
        "ARQOS",   "AWQOS",   "ARID",    "AWID",
        "BID",     "RID",     "WID"
    ]

    def __init__(self, entity, name, clock, memory, callback=None, event=None,
                 big_endian=False):

        BusDriver.__init__(self, entity, name, clock)
        self.clock = clock

        self.big_endian = big_endian
        self.bus.ARREADY.setimmediatevalue(1)
        self.bus.RVALID.setimmediatevalue(0)
        self.bus.RLAST.setimmediatevalue(0)
        self.bus.AWREADY.setimmediatevalue(1)
        self._memory = memory

        self.write_address_busy = Lock("%s_wabusy" % name)
        self.read_address_busy = Lock("%s_rabusy" % name)
        self.write_data_busy = Lock("%s_wbusy" % name)

        cocotb.fork(self._read_data())
        cocotb.fork(self._write_data())

    def _size_to_bytes_in_beat(self, AxSIZE):
        if AxSIZE < 7:
            return 2 ** AxSIZE
        return None

    @cocotb.coroutine
    def _write_data(self):
        clock_re = RisingEdge(self.clock)

        while True:
            while True:
                self.bus.WREADY <= 0
                yield ReadOnly()
                if self.bus.AWVALID.value:
                    self.bus.WREADY <= 1
                    break
                yield clock_re

            yield ReadOnly()
            _awaddr = int(self.bus.AWADDR)
            _awlen = int(self.bus.AWLEN)
            _awsize = int(self.bus.AWSIZE)
            _awburst = int(self.bus.AWBURST)
            _awprot = int(self.bus.AWPROT)

            burst_length = _awlen + 1
            bytes_in_beat = self._size_to_bytes_in_beat(_awsize)

            word = BinaryValue(n_bits=bytes_in_beat*8, bigEndian=self.big_endian)

            if __debug__:
                self.log.debug(
                    "AWADDR  %d\n" % _awaddr +
                    "AWLEN   %d\n" % _awlen +
                    "AWSIZE  %d\n" % _awsize +
                    "AWBURST %d\n" % _awburst +
                    "BURST_LENGTH %d\n" % burst_length +
                    "Bytes in beat %d\n" % bytes_in_beat)

            burst_count = burst_length

            yield clock_re

            while True:
                if self.bus.WVALID.value:
                    word = self.bus.WDATA.value
                    word.big_endian = self.big_endian
                    _burst_diff = burst_length - burst_count
                    _st = _awaddr + (_burst_diff * bytes_in_beat)  # start
                    _end = _awaddr + ((_burst_diff + 1) * bytes_in_beat)  # end
                    self._memory[_st:_end] = array.array('B', word.get_buff())
                    burst_count -= 1
                    if burst_count == 0:
                        break
                yield clock_re

    @cocotb.coroutine
    def _read_data(self):
        clock_re = RisingEdge(self.clock)

        while True:
            while True:
                yield ReadOnly()
                if self.bus.ARVALID.value:
                    break
                yield clock_re

            yield ReadOnly()
            _araddr = int(self.bus.ARADDR)
            _arlen = int(self.bus.ARLEN)
            _arsize = int(self.bus.ARSIZE)
            _arburst = int(self.bus.ARBURST)
            _arprot = int(self.bus.ARPROT)

            burst_length = _arlen + 1
            bytes_in_beat = self._size_to_bytes_in_beat(_arsize)

            word = BinaryValue(n_bits=bytes_in_beat*8, bigEndian=self.big_endian)

            if __debug__:
                self.log.debug(
                    "ARADDR  %d\n" % _araddr +
                    "ARLEN   %d\n" % _arlen +
                    "ARSIZE  %d\n" % _arsize +
                    "ARBURST %d\n" % _arburst +
                    "BURST_LENGTH %d\n" % burst_length +
                    "Bytes in beat %d\n" % bytes_in_beat)

            burst_count = burst_length

            yield clock_re

            while True:
                self.bus.RVALID <= 1
                yield ReadOnly()
                if self.bus.RREADY.value:
                    _burst_diff = burst_length - burst_count
                    _st = _araddr + (_burst_diff * bytes_in_beat)
                    _end = _araddr + ((_burst_diff + 1) * bytes_in_beat)
                    word.buff = self._memory[_st:_end].tostring()
                    self.bus.RDATA <= word
                    if burst_count == 1:
                        self.bus.RLAST <= 1
                yield clock_re
                burst_count -= 1
                self.bus.RLAST <= 0
                if burst_count == 0:
                    break



class AXI4StreamMaster(BusDriver):

    _signals = ["TVALID", "TREADY", "TDATA"]  # Write data channel
    _optional_signals = ["TLAST", "TKEEP", "TSTRB", "TID", "TDEST", "TUSER"]

    def __init__(self, entity, name, clock, width=32):
        BusDriver.__init__(self, entity, name, clock)
        #Drive default values onto bus
        self.width = width
        self.strobe_width = width / 8
        self.bus.TVALID.setimmediatevalue(0)
        self.bus.TLAST.setimmediatevalue(0)
        self.bus.TDATA.setimmediatevalue(0)
        self.bus.TKEEP.setimmediatevalue(0)
        self.bus.TID.setimmediatevalue(0)
        self.bus.TDEST.setimmediatevalue(0)
        self.bus.TUSER.setimmediatevalue(0)

        self.write_data_busy = Lock("%s_wbusy" % name)

    @cocotb.coroutine
    def write(self, data, byte_enable=-1, keep=1, tid=0, dest=0, user=0):
        """
        Send the write data, with optional delay
        """
        yield self.write_data_busy.acquire()
        self.bus.TVALID <=  0
        self.bus.TLAST  <=  0
        self.bus.TID    <=  tid
        self.bus.TDEST  <=  dest
        self.bus.TUSER  <=  user
        self.bus.TSTRB  <=  (1 << self.strobe_width) - 1
        if byte_enable == -1:
            byte_enable = (self.width >> 3) - 1

        #Wait for the slave to assert tready
        while True:
            yield ReadOnly()
            if self.bus.TREADY.value:
                break
            yield RisingEdge(self.clock)

        yield RisingEdge(self.clock)
        #every clock cycle update the data
        for i in range (len(data)):
            self.bus.TVALID <=  1
            self.bus.TDATA  <= data[i]
            if i >= len(data) - 1:
                self.bus.TLAST  <=  1;
            yield ReadOnly()
            if not self.bus.TREADY.value:
                while True:
                    yield RisingEdge(self.clock)
                    yield ReadOnly()
                    if self.bus.TREADY.value:
                        yield RisingEdge(self.clock)
                        break
                continue
            yield RisingEdge(self.clock)

        self.bus.TLAST  <=  0;
        self.bus.TVALID <=  0;
        yield RisingEdge(self.clock)
        self.write_data_busy.release()
        self.bus.TSTRB  <=  0


class AXI4StreamSlave(BusDriver):

    _signals = ["TVALID", "TREADY", "TDATA"]
    _optional_signals = ["TLAST", "TKEEP", "TSTRB", "TID", "TDEST", "TUSER"]

    def __init__(self, entity, name, clock, width = 32):
        BusDriver.__init__(self, entity, name, clock)
        self.width = width
        self.bus.TREADY <= 0;
        self.read_data_busy = Lock("%s_wbusy" % name)
        self.data = []

    @cocotb.coroutine
    def read(self, wait_for_valid = False):
        """Read a packe of data from the Axi Ingress stream"""
        yield self.read_data_busy.acquire()
        yield RisingEdge(self.clock)

        if wait_for_valid:
            while not self.bus.TVALID.value:
                #cocotb.log.info("Valid Not Detected")
                yield RisingEdge(self.clock)

            #cocotb.log.info("Found valid!")
            yield RisingEdge(self.clock)
            self.bus.TREADY <=  1

            while self.bus.TVALID.value:
                yield RisingEdge(self.clock)
                self.data.extend(self.bus.TDATA.value)
                if self.bus.TLAST.value:
                    break
        else:
            self.bus.TREADY <= 1

            while True:
                yield ReadOnly()
                yield RisingEdge(self.clock)
                if self.bus.TVALID.value:
                    cocotb.log.debug("Found Valid")
                    break
                yield RisingEdge(self.clock)


            while self.bus.TVALID.value:
                yield RisingEdge(self.clock)
                self.data.extend(self.bus.TDATA.value)
                if self.bus.TLAST.value:
                    break


