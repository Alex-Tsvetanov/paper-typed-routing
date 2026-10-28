<!-- The new loop's analysis (decision 21 (a)): t3/rr_results.py at ed3b7e0 over p2r3-rr-l's aa.jsonl and rr.jsonl, run on the desktop on 2026-10-28. Arch only; Windows (p2r3-rr-w) pending. The bring-ups' Release binaries at 3ff814e50, covered by p2r3-3ff814e50-L-asan, -tsan, -msan. Inputs and sha256s in rr-L.json. -->

# Round 3 in the new loop: median and standard deviation per contestant

## linux, campaign, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 3.09% of one CPU; a single idle server at most 0.619%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 127,145 | 382 | 7,865.0 | 23.6 | 10,036 | rank 1 |
| mserver | crow | 7 | 113,646 | 504 | 8,799.2 | 39.1 | 10,616 | rank 6 |
| mserver | drogon | 7 | 20,909 | 42 | 47,825.8 | 95.7 | 12,520 | rank 10 |
| mserver | oatpp | 7 | 53,737 | 26 | 18,609.3 | 8.8 | 10,796 | rank 9 |
| mserver | pistache | 7 | 105,561 | 174 | 9,473.2 | 15.6 | 10,728 | rank 7 |
| mserver | boost-url | 7 | 116,525 | 410 | 8,581.9 | 30.2 | 10,124 | rank 5 |
| mserver | r3 | 7 | 123,585 | 338 | 8,091.6 | 22.2 | 11,616 | rank 3 |
| mserver | uwebsockets | 7 | 124,611 | 315 | 8,025.0 | 20.2 | 10,016 | rank 2 |
| mserver | glaze | 7 | 117,385 | 250 | 8,519.0 | 18.1 | 11,184 | rank 4 |
| mserver | cpp-httplib | 7 | 60,650 | 119 | 16,488.1 | 32.4 | 10,316 | rank 8 |
| mserver | null | 7 | 129,071 | 310 | 7,747.7 | 18.5 | 9,740 |  |
| mserver-go | v2 | 7 | 59,017 | 174 | 16,944.2 | 50.2 | 23,328 | rank 1 |
| mserver-go | httprouter | 7 | 58,494 | 94 | 17,095.8 | 27.3 | 22,876 | rank 2 |
| mserver-go | gin | 7 | 57,200 | 141 | 17,482.6 | 43.0 | 23,324 | rank 3 |
| mserver-go | nethttp | 7 | 54,539 | 103 | 18,335.5 | 34.7 | 23,388 | rank 4 |
| mserver-go | chi | 7 | 53,016 | 135 | 18,862.2 | 48.0 | 23,356 | rank 5 |
| mserver-go | null | 7 | 60,822 | 95 | 16,441.5 | 25.7 | 23,036 |  |
| mserver-rs | v2 | 7 | 117,199 | 255 | 8,532.5 | 18.6 | 7,472 | rank 1 |
| mserver-rs | matchit | 7 | 116,659 | 353 | 8,572.0 | 25.9 | 8,272 | rank 2 |
| mserver-rs | path-tree | 7 | 115,606 | 396 | 8,650.1 | 29.8 | 8,084 | rank 3 |
| mserver-rs | actix-router | 7 | 15,315 | 30 | 65,293.7 | 127.4 | 29,540 | rank 4 |
| mserver-rs | null | 7 | 120,148 | 247 | 8,323.1 | 17.1 | 7,248 |  |

## linux, campaign, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 3.70% of one CPU; a single idle server at most 0.618%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 126,258 | 401 | 7,920.3 | 25.2 | 44,696 | rank 1 |
| mserver | crow | 7 | 103,522 | 346 | 9,659.8 | 32.2 | 75,968 | rank 5 |
| mserver | drogon | 7 | 98 | 2 | 10,204,569.2 | 217,794.8 | 294,628 | does not sustain the load |
| mserver | oatpp | 7 | 259 | 2 | 3,866,160.4 | 27,842.0 | 104,156 | rank 9 |
| mserver | pistache | 7 | 104,962 | 334 | 9,527.3 | 30.3 | 80,448 | rank 4 |
| mserver | boost-url | 7 | 37,874 | 80 | 26,403.4 | 55.9 | 62,464 | rank 7 |
| mserver | r3 | 7 | 116,652 | 504 | 8,572.5 | 37.0 | 181,104 | rank 2 |
| mserver | uwebsockets | 7 | 84,919 | 121 | 11,775.9 | 16.8 | 36,844 | rank 6 |
| mserver | glaze | 7 | 115,807 | 477 | 8,635.1 | 35.7 | 134,052 | rank 3 |
| mserver | cpp-httplib | 7 | 979 | 4 | 1,021,848.2 | 4,388.6 | 47,260 | rank 8 |
| mserver | null | 7 | 129,691 | 375 | 7,710.6 | 22.3 | 12,472 |  |
| mserver-go | v2 | 7 | 58,246 | 157 | 17,168.6 | 46.3 | 80,232 | rank 1 |
| mserver-go | httprouter | 7 | 49,050 | 249 | 20,387.3 | 102.7 | 79,508 | rank 3 |
| mserver-go | gin | 7 | 48,339 | 218 | 20,687.0 | 93.6 | 116,824 | rank 4 |
| mserver-go | nethttp | 7 | 49,725 | 751 | 20,110.4 | 300.8 | 163,672 | rank 2 |
| mserver-go | chi | 7 | 44,206 | 941 | 22,621.2 | 486.2 | 276,440 | rank 5 |
| mserver-go | null | 7 | 60,560 | 128 | 16,512.6 | 34.8 | 50,904 |  |
| mserver-rs | v2 | 7 | 116,499 | 421 | 8,583.8 | 31.1 | 76,664 | rank 1 |
| mserver-rs | matchit | 7 | 112,449 | 304 | 8,892.9 | 24.0 | 148,672 | rank 2 |
| mserver-rs | path-tree | 7 | 109,264 | 363 | 9,152.1 | 30.3 | 122,936 | rank 3 |
| mserver-rs | actix-router | 7 | 21 | 2 | 46,885,494.3 | 4,783,104.1 | 2,231,908 | does not sustain the load |
| mserver-rs | null | 7 | 120,079 | 177 | 8,327.9 | 12.3 | 45,844 |  |

## linux, A/A run, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 2.47% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 126,951 | 777 | 7,877.0 | 48.1 | 9,860 | entry 0 |
| mserver | v2 | 7 | 126,659 | 863 | 7,895.2 | 53.2 | 9,952 | entry 1 |
| mserver-go | v2 | 7 | 58,680 | 240 | 17,041.5 | 69.1 | 23,216 | entry 0 |
| mserver-go | v2 | 7 | 58,683 | 237 | 17,040.7 | 69.0 | 23,476 | entry 1 |
| mserver-rs | v2 | 7 | 117,427 | 556 | 8,515.9 | 40.1 | 7,296 | entry 0 |
| mserver-rs | v2 | 7 | 116,796 | 601 | 8,561.9 | 43.6 | 7,240 | entry 1 |

## linux, A/A run, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 2.47% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 126,418 | 392 | 7,910.2 | 24.4 | 44,800 | entry 0 |
| mserver | v2 | 7 | 126,867 | 468 | 7,882.3 | 29.2 | 44,636 | entry 1 |
| mserver-go | v2 | 7 | 58,004 | 131 | 17,240.3 | 38.9 | 79,936 | entry 0 |
| mserver-go | v2 | 7 | 58,217 | 152 | 17,177.1 | 44.8 | 80,184 | entry 1 |
| mserver-rs | v2 | 7 | 117,010 | 126 | 8,546.3 | 9.2 | 76,700 | entry 0 |
| mserver-rs | v2 | 7 | 124,504 | 311 | 8,031.9 | 20.1 | 76,412 | entry 1 |

