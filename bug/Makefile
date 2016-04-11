PWD := $(shell pwd)

VERILOG_SOURCES = $(PWD)/test_pkg.sv \
                  $(PWD)/testcase_top.sv

TOPLEVEL?=testcase_top
MODULE?=test_$(TOPLEVEL)


ASIM_ARGS += -L altera_mf_ver -L lpm_ver
VSIM_ARGS += -L altera_mf_ver -L lpm_ver

TOPLEVEL_LANG ?= verilog

# We only have modelsim 32-bit so globally force
ifeq ($(SIM),modelsim)
    ARCH=i686
endif

include $(COCOTB)/makefiles/Makefile.inc
include $(COCOTB)/makefiles/Makefile.sim
