<!-- The floor runs on Windows (Alex, 2026-10-28 and 29): t3/rr_results.py at d063274 over p2r3-rr-w2's aa.jsonl and rr.jsonl (p2r3-rr-w again, unchanged at ed3b7e0, chain A17, begun 62,328 s after boot) and p2r3-aa-w's rr-aak-W.jsonl (chain A17), run on the desktop on 2026-10-29. It replaces rr-W.json (chain A15). Host-spoiled rounds ran again once (decision 18): 2 A/A rounds, 3 campaign rounds and 1 k-server round. The floor is the rule fixed before the runs; the k-server run is descriptive. The bring-up's Release binaries at 3ff814e50, covered by p2r3-3ff814e50-W-asan. Inputs and sha256s in floor-W.json. -->

# Round 3 in the new loop: median and standard deviation per contestant

## windows, campaign, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 7.66% of one CPU; a single idle server at most 0.958%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 90,535 | 898 | 11,045.4 | 108.9 | 10,048 | rank 1 |
| mserver | crow | 7 | 78,175 | 475 | 12,791.9 | 77.5 | 10,844 | rank 6 |
| mserver | drogon | 7 | 32,202 | 40 | 31,054.4 | 38.6 | 11,260 | rank 8 |
| mserver | oatpp | 7 | 12,411 | 15 | 80,572.9 | 99.5 | 11,080 | rank 9 |
| mserver | pistache | 7 | 80,685 | 416 | 12,393.9 | 63.7 | 11,880 | rank 5 |
| mserver | boost-url | 7 | 82,819 | 508 | 12,074.5 | 74.1 | 10,436 | rank 3 |
| mserver | uwebsockets | 7 | 88,030 | 480 | 11,359.8 | 61.4 | 10,352 | rank 2 |
| mserver | glaze | 7 | 81,067 | 221 | 12,335.5 | 33.6 | 12,812 | rank 4 |
| mserver | cpp-httplib | 7 | 51,059 | 149 | 19,585.2 | 57.1 | 10,592 | rank 7 |
| mserver | null | 7 | 92,306 | 775 | 10,833.6 | 90.4 | 10,116 |  |
| mserver-go | v2 | 7 | 41,744 | 117 | 23,955.4 | 67.4 | 17,344 | rank 1 |
| mserver-go | httprouter | 7 | 41,002 | 189 | 24,389.3 | 113.1 | 16,868 | rank 2 |
| mserver-go | gin | 7 | 40,238 | 110 | 24,852.3 | 67.5 | 16,996 | rank 3 |
| mserver-go | nethttp | 7 | 38,817 | 162 | 25,762.0 | 107.5 | 17,288 | rank 4 |
| mserver-go | chi | 7 | 38,191 | 162 | 26,184.4 | 111.6 | 16,964 | rank 5 |
| mserver-go | null | 7 | 42,630 | 226 | 23,457.7 | 124.1 | 16,880 |  |
| mserver-rs | v2 | 7 | 70,993 | 158 | 14,086.0 | 31.2 | 6,688 | rank 1 |
| mserver-rs | matchit | 7 | 69,998 | 115 | 14,286.1 | 23.5 | 7,668 | rank 2 |
| mserver-rs | path-tree | 7 | 69,622 | 507 | 14,363.2 | 103.1 | 7,500 | rank 3 |
| mserver-rs | actix-router | 7 | 10,494 | 46 | 95,291.7 | 415.9 | 32,064 | rank 4 |
| mserver-rs | null | 7 | 71,916 | 48 | 13,905.1 | 9.3 | 7,000 |  |

## windows, campaign, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 8.64% of one CPU; a single idle server at most 0.955%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 90,069 | 623 | 11,102.5 | 76.0 | 41,324 | rank 1 |
| mserver | crow | 7 | 73,747 | 623 | 13,559.8 | 112.5 | 78,168 | rank 4 |
| mserver | drogon | 7 | 201 | 3 | 4,966,786.9 | 63,970.8 | 126,024 | rank 8 |
| mserver | oatpp | 7 | 56 | 2 | 17,830,869.4 | 493,594.7 | 110,668 | does not sustain the load |
| mserver | pistache | 7 | 76,650 | 591 | 13,046.3 | 99.6 | 168,640 | rank 3 |
| mserver | boost-url | 7 | 35,619 | 193 | 28,074.8 | 153.4 | 67,668 | rank 6 |
| mserver | uwebsockets | 7 | 61,979 | 345 | 16,134.4 | 90.1 | 41,812 | rank 5 |
| mserver | glaze | 7 | 77,384 | 427 | 12,922.6 | 72.1 | 261,376 | rank 2 |
| mserver | cpp-httplib | 7 | 584 | 2 | 1,710,985.9 | 5,280.7 | 52,412 | rank 7 |
| mserver | null | 7 | 91,992 | 869 | 10,870.6 | 102.0 | 16,708 |  |
| mserver-go | v2 | 7 | 41,288 | 79 | 24,220.3 | 46.6 | 68,868 | rank 1 |
| mserver-go | httprouter | 7 | 36,090 | 306 | 27,708.2 | 238.6 | 73,584 | rank 2 |
| mserver-go | gin | 7 | 35,724 | 247 | 27,992.1 | 191.5 | 91,748 | rank 3 |
| mserver-go | nethttp | 7 | 35,715 | 559 | 27,999.8 | 450.9 | 160,228 | rank 4 |
| mserver-go | chi | 7 | 32,736 | 396 | 30,547.5 | 372.6 | 249,592 | rank 5 |
| mserver-go | null | 7 | 42,544 | 261 | 23,505.1 | 145.3 | 38,168 |  |
| mserver-rs | v2 | 7 | 71,067 | 232 | 14,071.3 | 45.6 | 67,876 | rank 1 |
| mserver-rs | matchit | 7 | 68,317 | 303 | 14,637.7 | 64.6 | 140,616 | rank 2 |
| mserver-rs | path-tree | 7 | 67,911 | 303 | 14,725.2 | 65.7 | 116,572 | rank 3 |
| mserver-rs | actix-router | 7 | 20 | 2 | 50,497,423.3 | 4,410,646.1 | 2,341,212 | does not sustain the load |
| mserver-rs | null | 7 | 72,543 | 145 | 13,785.0 | 27.5 | 41,088 |  |

## windows, A/A run, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 4.84% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 89,676 | 3,571 | 11,151.2 | 466.9 | 9,992 | entry 0 |
| mserver | v2 | 7 | 89,402 | 2,991 | 11,185.4 | 388.5 | 9,992 | entry 1 |
| mserver-go | v2 | 7 | 40,158 | 1,559 | 24,901.5 | 987.3 | 17,080 | entry 0 |
| mserver-go | v2 | 7 | 40,940 | 1,761 | 24,426.3 | 1,118.1 | 17,344 | entry 1 |
| mserver-rs | v2 | 7 | 69,923 | 1,273 | 14,301.5 | 261.0 | 6,632 | entry 0 |
| mserver-rs | v2 | 7 | 71,015 | 1,434 | 14,081.5 | 294.6 | 6,608 | entry 1 |

## windows, A/A run, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 3.81% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 90,901 | 671 | 11,001.0 | 82.0 | 41,376 | entry 0 |
| mserver | v2 | 7 | 89,919 | 781 | 11,121.1 | 95.8 | 41,392 | entry 1 |
| mserver-go | v2 | 7 | 41,252 | 115 | 24,241.2 | 67.5 | 69,308 | entry 0 |
| mserver-go | v2 | 7 | 41,055 | 197 | 24,357.6 | 116.8 | 69,320 | entry 1 |
| mserver-rs | v2 | 7 | 70,479 | 150 | 14,188.7 | 30.2 | 67,912 | entry 0 |
| mserver-rs | v2 | 7 | 70,678 | 129 | 14,148.7 | 25.9 | 68,160 | entry 1 |

## windows, k-server A/A run, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 6.69% of one CPU; a single idle server at most 0.959%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 91,119 | 579 | 10,974.6 | 69.9 | 10,036 | entry 0 |
| mserver | v2 | 7 | 90,530 | 841 | 11,046.1 | 101.7 | 10,024 | entry 1 |
| mserver | v2 | 7 | 91,232 | 520 | 10,961.1 | 63.0 | 10,012 | entry 2 |
| mserver | v2 | 7 | 91,139 | 1,020 | 10,972.2 | 120.8 | 10,032 | entry 3 |
| mserver | v2 | 7 | 90,752 | 745 | 11,019.0 | 89.8 | 10,056 | entry 4 |
| mserver | v2 | 7 | 91,328 | 674 | 10,949.6 | 81.5 | 9,996 | entry 5 |
| mserver | v2 | 7 | 90,510 | 455 | 11,048.5 | 55.3 | 9,992 | entry 6 |
| mserver-go | v2 | 7 | 41,431 | 218 | 24,136.7 | 127.6 | 17,552 | entry 0 |
| mserver-go | v2 | 7 | 41,735 | 240 | 23,960.6 | 137.3 | 17,400 | entry 1 |
| mserver-go | v2 | 7 | 41,562 | 202 | 24,060.3 | 116.1 | 17,352 | entry 2 |
| mserver-go | v2 | 7 | 41,583 | 195 | 24,048.4 | 113.3 | 17,308 | entry 3 |
| mserver-go | v2 | 7 | 41,567 | 196 | 24,057.7 | 114.1 | 17,304 | entry 4 |
| mserver-go | v2 | 7 | 41,569 | 113 | 24,056.1 | 65.5 | 17,224 | entry 5 |
| mserver-go | v2 | 6 | 41,559 | 177 | 24,062.1 | 103.6 | 17,236 | entry 6 |
| mserver-rs | v2 | 7 | 71,042 | 135 | 14,076.1 | 26.8 | 6,552 | entry 0 |
| mserver-rs | v2 | 7 | 70,917 | 148 | 14,101.0 | 29.3 | 6,592 | entry 1 |
| mserver-rs | v2 | 7 | 70,819 | 53 | 14,120.5 | 10.6 | 6,620 | entry 2 |
| mserver-rs | v2 | 7 | 71,296 | 70 | 14,026.0 | 13.8 | 6,600 | entry 3 |
| mserver-rs | v2 | 7 | 71,305 | 463 | 14,024.2 | 90.6 | 6,660 | entry 4 |
| mserver-rs | v2 | 7 | 71,202 | 131 | 14,044.5 | 25.7 | 6,576 | entry 5 |
| mserver-rs | v2 | 7 | 71,105 | 204 | 14,063.6 | 40.3 | 6,656 | entry 6 |

mserver: the 7 entries' median ns per request span 98.9 (SD 41.2); within one process the pooled SD is 85.8; entry 0 ranks 4.
mserver-go: the 7 entries' median ns per request span 176.1 (SD 51.2); within one process the pooled SD is 113.3; entry 0 ranks 7.
mserver-rs: the 7 entries' median ns per request span 96.3 (SD 36.8); within one process the pooled SD is 42.1; entry 0 ranks 5.

## windows, k-server A/A run, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 5.72% of one CPU; a single idle server at most 0.959%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 91,342 | 742 | 10,947.8 | 88.6 | 41,400 | entry 0 |
| mserver | v2 | 7 | 90,745 | 559 | 11,019.9 | 68.4 | 41,456 | entry 1 |
| mserver | v2 | 7 | 91,210 | 885 | 10,963.7 | 106.1 | 41,408 | entry 2 |
| mserver | v2 | 7 | 89,393 | 705 | 11,186.5 | 87.7 | 41,452 | entry 3 |
| mserver | v2 | 7 | 90,965 | 462 | 10,993.2 | 55.5 | 41,436 | entry 4 |
| mserver | v2 | 7 | 91,158 | 705 | 10,970.0 | 85.3 | 41,464 | entry 5 |
| mserver | v2 | 7 | 91,152 | 742 | 10,970.7 | 88.3 | 41,464 | entry 6 |
| mserver-go | v2 | 7 | 41,255 | 285 | 24,239.3 | 167.3 | 68,888 | entry 0 |
| mserver-go | v2 | 7 | 41,098 | 125 | 24,331.8 | 73.4 | 70,980 | entry 1 |
| mserver-go | v2 | 7 | 40,980 | 204 | 24,402.4 | 121.2 | 69,772 | entry 2 |
| mserver-go | v2 | 7 | 41,080 | 239 | 24,342.9 | 141.5 | 70,692 | entry 3 |
| mserver-go | v2 | 7 | 41,031 | 109 | 24,371.9 | 64.9 | 71,080 | entry 4 |
| mserver-go | v2 | 7 | 41,195 | 104 | 24,274.6 | 61.3 | 69,624 | entry 5 |
| mserver-go | v2 | 7 | 41,265 | 198 | 24,233.5 | 117.2 | 69,384 | entry 6 |
| mserver-rs | v2 | 7 | 70,687 | 209 | 14,146.9 | 41.6 | 67,856 | entry 0 |
| mserver-rs | v2 | 7 | 70,752 | 306 | 14,133.9 | 60.7 | 68,212 | entry 1 |
| mserver-rs | v2 | 7 | 71,057 | 165 | 14,073.2 | 32.8 | 68,140 | entry 2 |
| mserver-rs | v2 | 7 | 71,053 | 154 | 14,074.1 | 30.4 | 68,180 | entry 3 |
| mserver-rs | v2 | 7 | 70,973 | 206 | 14,089.9 | 40.8 | 68,176 | entry 4 |
| mserver-rs | v2 | 7 | 70,657 | 343 | 14,152.9 | 69.1 | 68,160 | entry 5 |
| mserver-rs | v2 | 7 | 70,590 | 121 | 14,166.2 | 24.2 | 68,188 | entry 6 |

mserver: the 7 entries' median ns per request span 238.7 (SD 82.3); within one process the pooled SD is 84.2; entry 0 ranks 1.
mserver-go: the 7 entries' median ns per request span 169.0 (SD 65.7); within one process the pooled SD is 113.3; entry 0 ranks 2.
mserver-rs: the 7 entries' median ns per request span 93.0 (SD 39.5); within one process the pooled SD is 45.4; entry 0 ranks 5.

## windows, the floor: the A/A run's largest |d| against the campaign's neighbours

| Cell | Program | Ahead | Behind | Gap ns/req | A/A floor ns/req | Clears |
|---|---|---|---|---|---|---|
| mixed-disjoint/m1000/t111 | mserver | v2 | uwebsockets | 314.4 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver | uwebsockets | boost-url | 714.7 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver | boost-url | glaze | 261.0 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver | glaze | pistache | 58.5 | 200.3 | no |
| mixed-disjoint/m1000/t111 | mserver | pistache | crow | 397.9 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver | crow | cpp-httplib | 6,793.3 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver | cpp-httplib | drogon | 11,469.2 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver | drogon | oatpp | 49,518.5 | 200.3 | yes |
| mixed-disjoint/m1000/t111 | mserver-go | v2 | httprouter | 433.9 | 756.4 | no |
| mixed-disjoint/m1000/t111 | mserver-go | httprouter | gin | 463.0 | 756.4 | no |
| mixed-disjoint/m1000/t111 | mserver-go | gin | nethttp | 909.7 | 756.4 | yes |
| mixed-disjoint/m1000/t111 | mserver-go | nethttp | chi | 422.4 | 756.4 | no |
| mixed-disjoint/m1000/t111 | mserver-rs | v2 | matchit | 200.1 | 276.0 | no |
| mixed-disjoint/m1000/t111 | mserver-rs | matchit | path-tree | 77.1 | 276.0 | no |
| mixed-disjoint/m1000/t111 | mserver-rs | path-tree | actix-router | 80,928.5 | 276.0 | yes |
| mixed-disjoint/m100000/t111 | mserver | v2 | glaze | 1,820.1 | 167.8 | yes |
| mixed-disjoint/m100000/t111 | mserver | glaze | pistache | 123.6 | 167.8 | no |
| mixed-disjoint/m100000/t111 | mserver | pistache | crow | 513.5 | 167.8 | yes |
| mixed-disjoint/m100000/t111 | mserver | crow | uwebsockets | 2,574.6 | 167.8 | yes |
| mixed-disjoint/m100000/t111 | mserver | uwebsockets | boost-url | 11,940.3 | 167.8 | yes |
| mixed-disjoint/m100000/t111 | mserver | boost-url | cpp-httplib | 1,682,911.2 | 167.8 | yes |
| mixed-disjoint/m100000/t111 | mserver | cpp-httplib | drogon | 3,255,801.0 | 167.8 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | v2 | httprouter | 3,487.8 | 210.6 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | httprouter | gin | 283.9 | 210.6 | yes |
| mixed-disjoint/m100000/t111 | mserver-go | gin | nethttp | 7.6 | 210.6 | no |
| mixed-disjoint/m100000/t111 | mserver-go | nethttp | chi | 2,547.8 | 210.6 | yes |
| mixed-disjoint/m100000/t111 | mserver-rs | v2 | matchit | 566.3 | 107.2 | yes |
| mixed-disjoint/m100000/t111 | mserver-rs | matchit | path-tree | 87.5 | 107.2 | no |

