#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
int main(int argc, char** argv) {
    size_t n = (size_t)atol(argv[1]);  /* elements */
    int mode = atoi(argv[2]);
    size_t* next = malloc(n * sizeof(size_t));
    for (size_t i = 0; i < n; ++i) next[i] = i;
    uint64_t s = 88172645463325252ull;
    for (size_t i = n - 1; i > 0; --i) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; size_t j = s % i; size_t t = next[i]; next[i] = next[j]; next[j] = t; }
    size_t p = 0; uint64_t acc = 0;
    for (long k = 0; k < 50000000; ++k) {
        if (mode == 0) { p = next[p]; } else { acc = acc * 6364136223846793005ull + (uint64_t)k; }
    }
    printf("%zu %llu\n", p, (unsigned long long)acc);
    return 0;
}
