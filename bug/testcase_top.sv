module testcase_top #(
   parameter                                           DATA_WIDTH               = 128
)(
    input wire                                          clk,
    input wire                                          areset_n,

    input test_pkg::test_status_t [8:0]                 test_status,

    input [DATA_WIDTH-1:0]                              data_in_data,
    input                                               data_in_startofpacket,
    input                                               data_in_endofpacket,
    input [$clog2(DATA_WIDTH/8)-1:0]                    data_in_empty,
    input                                               data_in_valid,
    output                                              data_in_ready,

    output logic [DATA_WIDTH-1:0]                       data_out_data,
    output logic                                        data_out_startofpacket,
    output logic                                        data_out_endofpacket,
    output logic                                        data_out_channel,
    output logic [$clog2(DATA_WIDTH/8)-1:0]             data_out_empty,
    output logic                                        data_out_valid,
    input                                               data_out_ready
);


endmodule
