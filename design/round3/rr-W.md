<!-- The new loop's analysis (decision 21 (a)): t3/rr_results.py at ed3b7e0 over p2r3-rr-w's aa.jsonl and rr.jsonl (chain A15), run on the desktop on 2026-10-28. Host-spoiled rounds ran again once (decision 18): 2 A/A rounds and 7 campaign rounds; a rerun replaces its round for every contestant. The bring-up's Release binaries at 3ff814e50, covered by p2r3-3ff814e50-W-asan. Inputs and sha256s in rr-W.json. -->

# Round 3 in the new loop: median and standard deviation per contestant

## windows, campaign, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 6.70% of one CPU; a single idle server at most 0.957%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 91,225 | 621 | 10,961.9 | 74.5 | 10,032 | rank 1 |
| mserver | crow | 7 | 79,062 | 372 | 12,648.3 | 59.4 | 10,848 | rank 6 |
| mserver | drogon | 7 | 32,531 | 44 | 30,739.6 | 41.4 | 11,236 | rank 8 |
| mserver | oatpp | 7 | 12,710 | 50 | 78,677.8 | 313.0 | 11,032 | rank 9 |
| mserver | pistache | 6 | 80,670 | 461 | 12,396.2 | 70.7 | 11,888 | rank 5 |
| mserver | boost-url | 7 | 83,496 | 734 | 11,976.6 | 104.9 | 10,416 | rank 3 |
| mserver | uwebsockets | 7 | 89,297 | 820 | 11,198.6 | 102.8 | 10,352 | rank 2 |
| mserver | glaze | 7 | 81,435 | 206 | 12,279.8 | 31.1 | 12,772 | rank 4 |
| mserver | cpp-httplib | 7 | 51,489 | 150 | 19,421.5 | 56.7 | 10,548 | rank 7 |
| mserver | null | 7 | 93,385 | 459 | 10,708.3 | 52.5 | 10,124 |  |
| mserver-go | v2 | 7 | 40,883 | 176 | 24,460.3 | 105.4 | 17,064 | rank 1 |
| mserver-go | httprouter | 7 | 40,213 | 243 | 24,867.9 | 151.0 | 16,696 | rank 2 |
| mserver-go | gin | 7 | 39,818 | 114 | 25,114.0 | 72.1 | 16,928 | rank 3 |
| mserver-go | nethttp | 7 | 38,311 | 356 | 26,102.0 | 248.0 | 17,360 | rank 4 |
| mserver-go | chi | 7 | 36,794 | 260 | 27,178.3 | 194.1 | 17,060 | rank 5 |
| mserver-go | null | 6 | 42,058 | 660 | 23,776.5 | 387.2 | 16,808 |  |
| mserver-rs | v2 | 7 | 70,881 | 431 | 14,108.2 | 85.2 | 6,672 | rank 1 |
| mserver-rs | matchit | 7 | 70,734 | 509 | 14,137.5 | 101.1 | 7,624 | rank 2 |
| mserver-rs | path-tree | 7 | 70,296 | 203 | 14,225.6 | 41.0 | 7,452 | rank 3 |
| mserver-rs | actix-router | 7 | 10,377 | 14 | 96,363.5 | 127.8 | 32,004 | rank 4 |
| mserver-rs | null | 7 | 73,011 | 323 | 13,696.6 | 60.4 | 6,976 |  |

## windows, campaign, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 5.72% of one CPU; a single idle server at most 0.960%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 6 | 90,036 | 552 | 11,106.7 | 67.4 | 41,372 | rank 1 |
| mserver | crow | 7 | 75,919 | 287 | 13,172.0 | 49.6 | 78,188 | rank 4 |
| mserver | drogon | 7 | 197 | 2 | 5,065,023.4 | 41,359.7 | 126,012 | rank 8 |
| mserver | oatpp | 7 | 55 | 2 | 18,308,201.2 | 642,355.8 | 110,632 | does not sustain the load |
| mserver | pistache | 7 | 77,090 | 652 | 12,971.9 | 108.4 | 168,580 | rank 2 |
| mserver | boost-url | 7 | 35,767 | 142 | 27,958.7 | 111.4 | 67,680 | rank 6 |
| mserver | uwebsockets | 7 | 62,299 | 145 | 16,051.6 | 37.2 | 41,836 | rank 5 |
| mserver | glaze | 7 | 76,204 | 496 | 13,122.7 | 85.4 | 261,380 | rank 3 |
| mserver | cpp-httplib | 7 | 565 | 11 | 1,768,990.0 | 34,101.0 | 52,392 | rank 7 |
| mserver | null | 7 | 93,611 | 482 | 10,682.5 | 55.1 | 16,708 |  |
| mserver-go | v2 | 7 | 40,793 | 195 | 24,513.9 | 117.9 | 68,400 | rank 1 |
| mserver-go | httprouter | 7 | 35,280 | 299 | 28,344.9 | 239.1 | 80,872 | rank 4 |
| mserver-go | gin | 7 | 35,317 | 384 | 28,315.0 | 307.8 | 93,124 | rank 3 |
| mserver-go | nethttp | 7 | 35,586 | 639 | 28,101.3 | 518.3 | 154,736 | rank 2 |
| mserver-go | chi | 7 | 31,998 | 290 | 31,251.6 | 281.8 | 259,212 | rank 5 |
| mserver-go | null | 7 | 42,043 | 173 | 23,785.2 | 97.5 | 38,184 |  |
| mserver-rs | v2 | 7 | 71,715 | 545 | 13,944.1 | 105.4 | 67,936 | rank 1 |
| mserver-rs | matchit | 6 | 68,546 | 210 | 14,588.8 | 44.8 | 140,592 | rank 2 |
| mserver-rs | path-tree | 7 | 67,712 | 215 | 14,768.5 | 47.1 | 116,644 | rank 3 |
| mserver-rs | actix-router | 7 | 21 | 2 | 46,986,250.0 | 4,142,504.0 | 2,341,944 | does not sustain the load |
| mserver-rs | null | 7 | 73,368 | 185 | 13,629.9 | 34.3 | 41,140 |  |

## windows, A/A run, mixed-disjoint/m1000/t111

7 rounds. Other processes at most 5.76% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 90,632 | 2,379 | 11,033.6 | 302.4 | 9,984 | entry 0 |
| mserver | v2 | 7 | 88,772 | 2,484 | 11,264.8 | 317.3 | 9,984 | entry 1 |
| mserver-go | v2 | 7 | 40,983 | 1,556 | 24,400.4 | 993.6 | 17,096 | entry 0 |
| mserver-go | v2 | 7 | 40,357 | 1,134 | 24,778.7 | 717.5 | 17,164 | entry 1 |
| mserver-rs | v2 | 7 | 70,955 | 1,313 | 14,093.5 | 261.6 | 6,636 | entry 0 |
| mserver-rs | v2 | 7 | 71,446 | 1,170 | 13,996.6 | 236.2 | 6,628 | entry 1 |

## windows, A/A run, mixed-disjoint/m100000/t111

7 rounds. Other processes at most 4.80% of one CPU; a single idle server at most 0.000%.

| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |
|---|---|---|---|---|---|---|---|---|
| mserver | v2 | 7 | 90,580 | 1,098 | 11,040.0 | 136.2 | 41,436 | entry 0 |
| mserver | v2 | 7 | 90,983 | 544 | 10,991.0 | 66.1 | 41,456 | entry 1 |
| mserver-go | v2 | 7 | 40,893 | 149 | 24,454.1 | 89.3 | 68,548 | entry 0 |
| mserver-go | v2 | 7 | 40,841 | 172 | 24,485.2 | 103.5 | 68,984 | entry 1 |
| mserver-rs | v2 | 7 | 71,459 | 247 | 13,994.1 | 48.3 | 67,848 | entry 0 |
| mserver-rs | v2 | 7 | 71,832 | 249 | 13,921.3 | 48.6 | 68,232 | entry 1 |

