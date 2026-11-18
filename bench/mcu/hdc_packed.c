#include "hdc_packed.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HDC_CODE_ATTR IRAM_ATTR
#else
#define HDC_CODE_ATTR
#endif
#define INLINE static inline __attribute__((always_inline))
INLINE unsigned pop32(uint32_t x) {
    x=x-((x>>1)&0x55555555u);
    x=(x&0x33333333u)+((x>>2)&0x33333333u);
    x=(x+(x>>4))&0x0f0f0f0fu;
    return (x*0x01010101u)>>24;
}
INLINE unsigned trailing_zeroes(unsigned t) {
    unsigned k=0;while((t&1u)==0){k++;t>>=1;}return k;
}
void hdc_init(hdc_context *ctx) {
    for(unsigned k=0;k<13;k++)for(unsigned w=0;w<HDC_WORDS;w++)ctx->flip[k][w]=0;
    for(unsigned i=0;i<HDC_FEATURES;i++) {
        unsigned row=(1597u*(i+1u))&(HDC_DIM-1u);
        for(unsigned k=0;k<13;k++)if((row>>k)&1u)ctx->flip[k][i/32]|=1u<<(i%32);
    }
}
/* Packed feature lanes and packed bit-plane class counters, no desktop ISA
 * extensions and no stored feature-HV table. Same >=96 bundling rule. */
__attribute__((noinline,noclone)) HDC_CODE_ATTR unsigned hdc_packed32(const hdc_context *ctx,
 const uint32_t *model,const uint8_t *features,unsigned classes,
 uint16_t *scores,uint32_t *query) {
    uint32_t group[4][HDC_WORDS];uint32_t h[HDC_WORDS];uint32_t planes[14];
    for(unsigned l=0;l<4;l++)for(unsigned w=0;w<HDC_WORDS;w++)group[l][w]=0;
    for(unsigned w=0;w<HDC_WORDS;w++)h[w]=0;
    for(unsigned b=0;b<14;b++)planes[b]=0;
    for(unsigned i=0;i<HDC_FEATURES;i++)group[features[i]][i/32]|=1u<<(i%32);
    uint32_t class_mask=(1u<<classes)-1u;
    for(unsigned t=0;t<HDC_DIM;t++) {
        if(t) {
            unsigned k=trailing_zeroes(t);
            for(unsigned w=0;w<HDC_WORDS;w++)h[w]^=ctx->flip[k][w];
        }
        unsigned j=t^(t>>1);uint32_t word=model[j];
        uint32_t s0=0u-(word&1u),s1=0u-((word>>1)&1u);
        uint32_t s2=0u-((word>>2)&1u),s3=0u-((word>>3)&1u);
        unsigned count=0;
        for(unsigned w=0;w<HDC_WORDS;w++) {
            uint32_t level=(s0&group[0][w])|(s1&group[1][w])|
                           (s2&group[2][w])|(s3&group[3][w]);
            count+=pop32(h[w]^level);
        }
        unsigned q=count>=96;
        if(query)query[j/32]|=(uint32_t)q<<(j%32);
        uint32_t carry=((word>>4)^(0u-(q^1u)))&class_mask;
        for(unsigned b=0;carry && b<14;b++) {
            uint32_t old=planes[b];planes[b]=old^carry;carry&=old;
        }
    }
    unsigned winner=0,best=0;
    for(unsigned k=0;k<classes;k++) {
        unsigned score=0;
        for(unsigned b=0;b<14;b++)score|=((planes[b]>>k)&1u)<<b;
        scores[k]=(uint16_t)score;
        if(score>best){best=score;winner=k;}
    }
    return winner;
}
