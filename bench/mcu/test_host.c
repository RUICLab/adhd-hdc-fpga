#include <stdio.h>
#include <string.h>
#include "hdc_packed.h"
#include "vectors_k10.h"
#include "vectors_k26.h"
static hdc_context ctx;
static uint32_t query[HDC_QUERY_WORDS];
static uint16_t scores[26];
static unsigned tests=0;
static int check(unsigned k,unsigned id,const uint32_t *m,const uint8_t *v,
                 const uint32_t *q,const uint16_t *s) {
    unsigned expected=0;for(unsigned c=1;c<k;c++)if(s[c]>s[expected])expected=c;
    memset(query,0,sizeof(query));
    unsigned winner=hdc_packed32(&ctx,m,v,k,scores,query);
    if(winner!=expected || memcmp(scores,s,k*sizeof(*s)) || memcmp(query,q,sizeof(query))) {
        printf("FAIL K=%u case=%u query/score/winner\n",k,id);return 1;
    }
    winner=hdc_packed32(&ctx,m,v,k,scores,0);
    if(winner!=expected || memcmp(scores,s,k*sizeof(*s)))return 1;
    tests++;printf("PASS MCU-C K=%u case=%u winner=%u score=%u\n",k,id,winner,scores[winner]);
    return 0;
}
#define CHECK(K,I) if(check(K,I,k##K##_case##I##_model,k##K##_case##I##_features,k##K##_case##I##_query,k##K##_case##I##_scores))return 1
int main(void) {
    hdc_init(&ctx);
    CHECK(10,0);CHECK(10,1);CHECK(10,2);CHECK(10,3);
    CHECK(26,0);CHECK(26,1);CHECK(26,2);CHECK(26,3);
    printf("PASS MCU-C: %u cases; all 65536 query bits, scores and winners; query-free path matches\n",tests);
    return 0;
}
