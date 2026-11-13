# Classifier interface

`adhd_hdc` uses one rising-edge clock and synchronous active-low `resetn`.
Defaults are `DIM_BITS=13`, `FEATURES=196`, `CLASSES=10`, `STRIDE=1597`,
`THRESHOLD=96`. Published tests cover 8192 dimensions and K=10/26; CPU code
uses K=10. Other parameter combinations are not characterized.

## Loading inputs

After reset, `ready` is high. Initialize **all** model words and features
before asserting `start`; neither memory is cleared by reset. Writes require
`resetn && ready && !start`. Busy writes and starts are ignored.

| Ports | Operation |
|---|---|
| `model_we`, `model_addr[12:0]`, `model_data[31:0]` | Write one dimension's four level bits and class prototype bits |
| `feature_we`, `feature_addr[7:0]`, `feature_data[1:0]` | Write one of 196 features, with level index 0..3 |
| `start` | Pulse for one cycle while `ready` to begin inference |
| `ready`, `busy` | Core accepts new work only when ready; busy remains high while holding an unaccepted result |
| `result_valid`, `result_ready` | Result handshake; class and score remain stable until accepted |
| `result_class[4:0]`, `result_score[13:0]` | Winning class index and number of matching dimensions |
| `cycles[31:0]` | Active inference cycle count, excluding model/feature loading and result hold time |
| `query_valid`, `query_addr[12:0]`, `query_bit` | Verification stream in Gray-address order |

For natural dimension `j`, model word `j` is packed as:

```text
bit 0..3     : level hypervectors L0[j], L1[j], L2[j], L3[j]
bit 4+k      : prototype Pk[j], for class k = 0..CLASSES-1
unused bits  : ignored
```

The 32-bit model port supports the characterized 10/26-class configurations.
Feature addresses 196..255 are ignored. Model addressing follows `DIM_BITS`.
Scores range from 0 to 8192 inclusive, requiring 14 bits. Ties select the
lowest class index. Result latency is `D + 5 + K` cycles, where `D=2^DIM_BITS`.

Reset can abort an active inference and clears pipeline/results/counters,
while retaining the loaded memories. After a result handshake, wait for
`ready` before loading or starting the next inference. The core has no AXI,
DMA, sensor, or processor driver. The supplied board harness exercises the
same ports using initialized fixture ROMs.
