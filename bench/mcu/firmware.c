#include "hdc_packed.h"
#include "vectors_k10.h"
#include "vectors_k26.h"
static volatile uint32_t *const out=(volatile uint32_t *)0x10000000u;
static uint32_t model[HDC_DIM],query[HDC_QUERY_WORDS];
static uint8_t features[HDC_FEATURES];
static uint16_t scores[26];
static hdc_context ctx;
static inline uint32_t cycle(void){uint32_t n;__asm__ volatile("rdcycle %0":"=r"(n)::"memory");return n;}
static inline uint32_t instret(void){uint32_t n;__asm__ volatile("rdinstret %0":"=r"(n)::"memory");return n;}
static void fail(unsigned code){out[15]=code;for(;;){}}
static void verify(unsigned k,const uint32_t *m,const uint8_t *v,const uint32_t *q,const uint16_t *s){
    for(unsigned j=0;j<HDC_DIM;j++)model[j]=m[j];
    for(unsigned i=0;i<HDC_FEATURES;i++)features[i]=v[i];
    for(unsigned w=0;w<HDC_QUERY_WORDS;w++)query[w]=0;
    unsigned expected=0;for(unsigned c=1;c<k;c++)if(s[c]>s[expected])expected=c;
    unsigned winner=hdc_packed32(&ctx,model,features,k,scores,query);
    if(winner!=expected)fail(0x1000u+k);
    for(unsigned c=0;c<k;c++)if(scores[c]!=s[c])fail(0x2000u+k);
    for(unsigned w=0;w<HDC_QUERY_WORDS;w++)if(query[w]!=q[w])fail(0x3000u+k);
    out[0]=k;out[8]=1;
}
static void measure(unsigned k,const uint16_t *expected){
    uint32_t e0=cycle(),ei0=instret(),ei1=instret(),e1=cycle();
    uint32_t c0=cycle(),i0=instret();
    unsigned winner=hdc_packed32(&ctx,model,features,k,scores,0);
    uint32_t i1=instret(),c1=cycle();
    for(unsigned c=0;c<k;c++)if(scores[c]!=expected[c])fail(0x4000u+k);
    out[0]=k;out[1]=c1-c0;out[2]=e1-e0;
    out[3]=(i1-i0)-(ei1-ei0);out[4]=winner;out[5]=scores[winner];out[8]=2;
}
int main(void){
    hdc_init(&ctx);
    verify(10,k10_case0_model,k10_case0_features,k10_case0_query,k10_case0_scores);
    verify(10,k10_case2_model,k10_case2_features,k10_case2_query,k10_case2_scores);
    measure(10,k10_case2_scores);
    verify(26,k26_case0_model,k26_case0_features,k26_case0_query,k26_case0_scores);
    verify(26,k26_case2_model,k26_case2_features,k26_case2_query,k26_case2_scores);
    measure(26,k26_case2_scores);
    out[15]=0x600d600du;
    for(;;){}
}
