<!-- The floor runs on Arch (Alex, 2026-10-28 and 29): t3/rr_results.py at d063274 over p2r3-rr-l's aa.jsonl and rr.jsonl (chain A12, the records of rr-L.json) and p2r3-aa-l's rr-aak-L.jsonl (chain A17, begun 29 s after boot), run on the desktop on 2026-10-29. No round ran again. The floor is the rule fixed before the runs; the k-server run is descriptive. The bring-up's Release binaries at 3ff814e50, covered by p2r3-3ff814e50-L-asan, -tsan and -msan. Inputs and sha256s in floor-L.json. -->

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

## linux, k-server A/A run, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 2.47% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 126,167 | 356 | 7,926.0 | 22.4 | 10,028 | entry 0 |
| mserver | v2 | 7 | 125,632 | 520 | 7,959.8 | 32.8 | 10,044 | entry 1 |
| mserver | v2 | 7 | 126,108 | 356 | 7,929.7 | 22.4 | 9,876 | entry 2 |
| mserver | v2 | 7 | 126,582 | 198 | 7,900.0 | 12.4 | 9,792 | entry 3 |
| mserver | v2 | 7 | 126,670 | 205 | 7,894.5 | 12.7 | 9,932 | entry 4 |
| mserver | v2 | 7 | 126,536 | 272 | 7,902.9 | 17.1 | 10,040 | entry 5 |
| mserver | v2 | 7 | 126,315 | 350 | 7,916.7 | 21.9 | 10,072 | entry 6 |
| mserver-go | v2 | 7 | 58,360 | 97 | 17,135.1 | 28.5 | 23,600 | entry 0 |
| mserver-go | v2 | 7 | 58,360 | 102 | 17,135.1 | 30.0 | 23,420 | entry 1 |
| mserver-go | v2 | 7 | 58,047 | 128 | 17,227.4 | 37.8 | 23,644 | entry 2 |
| mserver-go | v2 | 7 | 58,545 | 117 | 17,080.9 | 34.3 | 23,164 | entry 3 |
| mserver-go | v2 | 7 | 58,294 | 125 | 17,154.5 | 36.8 | 23,324 | entry 4 |
| mserver-go | v2 | 7 | 58,506 | 60 | 17,092.1 | 17.6 | 23,572 | entry 5 |
| mserver-go | v2 | 7 | 58,312 | 87 | 17,149.0 | 25.7 | 23,396 | entry 6 |
| mserver-rs | v2 | 7 | 117,432 | 190 | 8,515.6 | 13.8 | 7,108 | entry 0 |
| mserver-rs | v2 | 7 | 117,402 | 379 | 8,517.8 | 27.6 | 7,368 | entry 1 |
| mserver-rs | v2 | 7 | 117,520 | 379 | 8,509.2 | 27.4 | 7,368 | entry 2 |
| mserver-rs | v2 | 7 | 117,044 | 282 | 8,543.8 | 20.6 | 7,372 | entry 3 |
| mserver-rs | v2 | 7 | 116,584 | 177 | 8,577.5 | 13.0 | 7,068 | entry 4 |
| mserver-rs | v2 | 7 | 117,281 | 420 | 8,526.5 | 30.4 | 7,360 | entry 5 |
| mserver-rs | v2 | 7 | 116,670 | 341 | 8,571.2 | 25.1 | 7,364 | entry 6 |

mserver: the 7 entries' median ns per request span 65.2 (SD 22.5); within one process the pooled SD is 21.3; entry 0 ranks 5.
mserver-go: the 7 entries' median ns per request span 146.5 (SD 47.9); within one process the pooled SD is 30.8; entry 0 ranks 4.
mserver-rs: the 7 entries' median ns per request span 68.4 (SD 27.6); within one process the pooled SD is 23.5; entry 0 ranks 2.

## linux, k-server A/A run, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 2.47% of one CPU; a single idle server at most 0.618%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 125,784 | 358 | 7,950.2 | 22.7 | 44,696 | entry 0 |
| mserver | v2 | 7 | 125,856 | 422 | 7,945.6 | 26.6 | 44,608 | entry 1 |
| mserver | v2 | 7 | 125,641 | 418 | 7,959.2 | 26.6 | 44,664 | entry 2 |
| mserver | v2 | 7 | 125,931 | 268 | 7,940.8 | 16.9 | 44,784 | entry 3 |
| mserver | v2 | 7 | 125,944 | 270 | 7,940.0 | 17.0 | 44,668 | entry 4 |
| mserver | v2 | 7 | 125,778 | 389 | 7,950.5 | 24.6 | 44,776 | entry 5 |
| mserver | v2 | 7 | 126,015 | 422 | 7,935.6 | 26.6 | 44,612 | entry 6 |
| mserver-go | v2 | 7 | 57,731 | 85 | 17,321.7 | 25.5 | 79,980 | entry 0 |
| mserver-go | v2 | 7 | 58,101 | 118 | 17,211.4 | 35.0 | 80,196 | entry 1 |
| mserver-go | v2 | 7 | 57,854 | 193 | 17,285.0 | 57.8 | 80,264 | entry 2 |
| mserver-go | v2 | 7 | 58,096 | 174 | 17,213.0 | 51.3 | 80,180 | entry 3 |
| mserver-go | v2 | 7 | 58,278 | 121 | 17,159.2 | 35.8 | 79,980 | entry 4 |
| mserver-go | v2 | 7 | 57,986 | 172 | 17,245.7 | 51.1 | 79,964 | entry 5 |
| mserver-go | v2 | 7 | 58,113 | 90 | 17,207.8 | 26.6 | 80,272 | entry 6 |
| mserver-rs | v2 | 7 | 116,026 | 365 | 8,618.7 | 27.0 | 76,720 | entry 0 |
| mserver-rs | v2 | 7 | 116,479 | 361 | 8,585.2 | 26.5 | 76,684 | entry 1 |
| mserver-rs | v2 | 7 | 116,174 | 239 | 8,607.8 | 17.7 | 76,476 | entry 2 |
| mserver-rs | v2 | 7 | 116,227 | 462 | 8,603.9 | 34.4 | 76,700 | entry 3 |
| mserver-rs | v2 | 7 | 117,316 | 275 | 8,524.0 | 19.9 | 76,472 | entry 4 |
| mserver-rs | v2 | 7 | 116,583 | 214 | 8,577.5 | 15.7 | 76,840 | entry 5 |
| mserver-rs | v2 | 7 | 116,706 | 349 | 8,568.5 | 25.5 | 76,684 | entry 6 |

mserver: the 7 entries' median ns per request span 23.6 (SD 8.0); within one process the pooled SD is 23.4; entry 0 ranks 5.
mserver-go: the 7 entries' median ns per request span 162.5 (SD 54.2); within one process the pooled SD is 42.2; entry 0 ranks 7.
mserver-rs: the 7 entries' median ns per request span 94.7 (SD 31.7); within one process the pooled SD is 24.6; entry 0 ranks 7.

## linux, the floor: the A/A run's largest |d| against the campaign's neighbours

| Cell | Program | Ahead | Behind | Gap ns/req | A/A floor ns/req | Clears |
|---|---|---|---|---|---|---|
| mixed-disjoint/m1000/t111 | mserver | v2 | uwebsockets | 159.9 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | uwebsockets | r3 | 66.6 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | r3 | glaze | 427.4 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | glaze | boost-url | 62.9 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | boost-url | crow | 217.4 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | crow | pistache | 674.0 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | pistache | cpp-httplib | 7,014.9 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | cpp-httplib | oatpp | 2,121.2 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver | oatpp | drogon | 29,216.5 | 34.5 | yes |
| mixed-disjoint/m1000/t111 | mserver-go | v2 | httprouter | 151.6 | 124.6 | yes |
| mixed-disjoint/m1000/t111 | mserver-go | httprouter | gin | 386.7 | 124.6 | yes |
| mixed-disjoint/m1000/t111 | mserver-go | gin | nethttp | 852.9 | 124.6 | yes |
| mixed-disjoint/m1000/t111 | mserver-go | nethttp | chi | 526.8 | 124.6 | yes |
| mixed-disjoint/m1000/t111 | mserver-rs | v2 | matchit | 39.5 | 61.2 | no |
| mixed-disjoint/m1000/t111 | mserver-rs | matchit | path-tree | 78.1 | 61.2 | yes |
| mixed-disjoint/m1000/t111 | mserver-rs | path-tree | actix-router | 56,643.6 | 61.2 | yes |
| mixed-disjoint/m100000/t111 | mserver | v2 | r3 | 652.2 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | r3 | glaze | 62.5 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | glaze | pistache | 892.2 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | pistache | crow | 132.5 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | crow | uwebsockets | 2,116.1 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | uwebsockets | boost-url | 14,627.6 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | boost-url | cpp-httplib | 995,444.8 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver | cpp-httplib | oatpp | 2,844,312.2 | 46.9 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | v2 | nethttp | 2,941.8 | 150.1 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | nethttp | httprouter | 276.9 | 150.1 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | httprouter | gin | 299.7 | 150.1 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | gin | chi | 1,934.2 | 150.1 | yes |
| mixed-disjoint/m100000/t111 | mserver-rs | v2 | matchit | 309.1 | 540.3 | no |
| mixed-disjoint/m100000/t111 | mserver-rs | matchit | path-tree | 259.2 | 540.3 | no |

