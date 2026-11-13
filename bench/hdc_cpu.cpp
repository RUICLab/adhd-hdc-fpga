// Exact binary HDC CPU reference implementations and compute benchmarks.
// Build: g++ -O3 -march=native -std=c++17 bench/hdc_cpu.cpp -o build/hdc_cpu.exe
// Run: build/hdc_cpu.exe PATH_TO_GENERATED_XSIM_VECTORS
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#endif
constexpr int D=8192,N=196,K=10,W=D/64;
using Features=std::array<uint8_t,N>;
using Image=std::array<uint8_t,1024>;
std::array<std::array<int8_t,9>,4> filters;
__attribute__((noinline)) Features regional(const Image& image){
 Features v{};
 for(int u=0;u<14;u++)for(int w=0;w<14;w++){
  int base=(2+2*u)*32+2+2*w;
  int sum=image[base]+image[base+1]+image[base+32]+image[base+33];
  v[u*14+w]=(sum>=256)+(sum>=512)+(sum>=768);
 }return v;
}
__attribute__((noinline)) Features convolutional(const Image& image){
 Features v{};
 for(int c=0;c<4;c++){
  std::array<int32_t,28*28> conv{};
  for(int y=0;y<28;y++)for(int x=0;x<28;x++)
   for(int m=0;m<3;m++)for(int n=0;n<3;n++)
    conv[y*28+x]+=int(image[(y+m+1)*32+x+n+1])*filters[c][m*3+n];
  for(int u=0;u<7;u++)for(int w=0;w<7;w++){
   int sum=0;
   for(int a=0;a<4;a++)for(int b=0;b<4;b++)sum+=conv[(4*u+a)*28+4*w+b];
   // Pool factor 1/16 is absorbed into these synthetic thresholds.
   v[c*49+u*7+w]=(sum>=-40000)+(sum>=0)+(sum>=40000);
  }
 }return v;
}
Features convolutional_reference(const Image& image){
 Features v{};
 for(int c=0;c<4;c++)for(int u=0;u<7;u++)for(int w=0;w<7;w++){
  int sum=0;
  for(int a=0;a<4;a++)for(int b=0;b<4;b++)for(int m=0;m<3;m++)for(int n=0;n<3;n++)
   sum+=int(image[(4*u+a+m+1)*32+4*w+b+n+1])*filters[c][m*3+n];
  v[c*49+u*7+w]=(sum>=-40000)+(sum>=0)+(sum>=40000);
 }return v;
}
struct Result {std::array<uint64_t,W> q{};std::array<int,K> score{};};
struct Model {
 std::array<std::array<uint8_t,D>,4> level{};
 std::array<std::array<uint64_t,W>,K> proto{};
};
std::vector<std::array<uint8_t,D>> hadamard(N);
std::vector<unsigned> readhex(const std::string& filename) {
 std::ifstream f(filename); if(!f)throw std::runtime_error(filename);
 std::vector<unsigned> v;unsigned x;while(f>>std::hex>>x)v.push_back(x);return v;
}
Model load(const std::vector<unsigned>& words) {
 if(words.size()!=D)throw std::runtime_error("model length");Model m;
 for(int j=0;j<D;j++){
  for(int l=0;l<4;l++)m.level[l][j]=(words[j]>>l)&1;
  for(int k=0;k<K;k++)m.proto[k][j/64]|=uint64_t((words[j]>>(4+k))&1)<<(j%64);
 }return m;
}
void classify(Result& r,const Model& m){
 for(int k=0;k<K;k++)for(int w=0;w<W;w++)
  r.score[k]+=64-__builtin_popcountll(r.q[w]^m.proto[k][w]);
}
__attribute__((noinline)) Result direct(const Features& v,const Model& m){
 Result r;
 for(int j=0;j<D;j++){
  unsigned c=0;
  for(int i=0;i<N;i++)c+=__builtin_parity(unsigned((1597*(i+1))%D)&unsigned(j))^m.level[v[i]][j];
  r.q[j/64]|=uint64_t(c>=96)<<(j%64);
 }classify(r,m);return r;
}
__attribute__((noinline)) Result lookup(const Features& v,const Model& m){
 // Explicit feature HV storage is a CPU speed/storage tradeoff (1.53125 MiB).
 std::array<uint8_t,D> count{};Result r;
 for(int i=0;i<N;i++){
  const auto& h=hadamard[i];const auto& l=m.level[v[i]];
  for(int j=0;j<D;j++)count[j]+=h[j]^l[j];
 }
 for(int j=0;j<D;j++)r.q[j/64]|=uint64_t(count[j]>=96)<<(j%64);
 classify(r,m);return r;
}
__attribute__((noinline)) Result fwht(const Features& v,const Model& m){
 // Exact regrouping using the specified Sylvester Hadamard encoder.
 // 0->+1, 1->-1, so count>=96 is equivalent to signed sum<=4.
 std::array<std::array<int16_t,D>,4> a{};Result r;
 for(int i=0;i<N;i++)a[v[i]][(1597*(i+1))%D]++;
 for(auto& l:a)for(int len=1;len<D;len*=2)
  for(int base=0;base<D;base+=2*len)for(int j=0;j<len;j++){
   int x=l[base+j],y=l[base+j+len];l[base+j]=x+y;l[base+j+len]=x-y;
  }
 for(int j=0;j<D;j++){
  int sum=0;for(int l=0;l<4;l++)sum+=m.level[l][j]?-a[l][j]:a[l][j];
  r.q[j/64]|=uint64_t(sum<=4)<<(j%64);
 }classify(r,m);return r;
}
volatile uint64_t checksum=0;
using Fn=Result(*)(const Features&,const Model&);
void bench(const char* name,Fn fn,const std::array<Features,64>& inputs,const Model& model){
 for(int n=0;n<64;n++){auto r=fn(inputs[n],model);checksum+=r.q[n%W]+r.score[n%K];}
 std::vector<double> times;
 for(int repeat=0;repeat<9;repeat++){
  auto start=std::chrono::steady_clock::now();
  for(int n=0;n<256;n++){auto r=fn(inputs[n%64],model);checksum+=r.q[n%W]+r.score[n%K];}
  auto end=std::chrono::steady_clock::now();
  times.push_back(std::chrono::duration<double,std::micro>(end-start).count()/256);
 }
 auto sorted=times;std::sort(sorted.begin(),sorted.end());
 std::cout<<name<<" median_us="<<sorted[4]<<" min_us="<<sorted.front()<<" max_us="<<sorted.back()<<" trials_us=";
 for(auto v:times)std::cout<<v<<",";
 std::cout<<" fpga_core_speedup="<<sorted[4]/82.07<<"\n";
}
using Front=Features(*)(const Image&);
void bench_front(const char* name,Front front,const std::array<Image,64>& images,const Model& model,bool hdc){
 auto consume=[&](int n){auto v=front(images[n%64]);
  if(hdc){auto r=fwht(v,model);checksum+=r.q[n%W]+r.score[n%K];}
  else checksum+=v[n%N];};
 for(int n=0;n<64;n++)consume(n);
 std::vector<double> times;
 for(int repeat=0;repeat<9;repeat++){
  auto begin=std::chrono::steady_clock::now();for(int n=0;n<256;n++)consume(n);
  auto end=std::chrono::steady_clock::now();
  times.push_back(std::chrono::duration<double,std::micro>(end-begin).count()/256);
 }
 auto sorted=times;std::sort(sorted.begin(),sorted.end());
 std::cout<<name<<" median_us="<<sorted[4]<<" min_us="<<sorted.front()<<" max_us="<<sorted.back()<<" trials_us=";
 for(auto v:times)std::cout<<v<<",";std::cout<<"\n";
}
int main(int argc,char** argv){try{
 if(argc!=2)throw std::runtime_error("Supply generated K=10 D=8192 vector directory");
#ifdef _WIN32
 bool pinned=SetThreadAffinityMask(GetCurrentThread(),DWORD_PTR(1))!=0;
 std::cout<<"single_thread=1 affinity_logical_cpu0="<<pinned<<"\n";
#endif
 for(int i=0;i<N;i++)for(int j=0;j<D;j++)hadamard[i][j]=__builtin_parity(unsigned((1597*(i+1))%D)&unsigned(j));
 std::string folder=argv[1];
 for(int test=0;test<4;test++){
  auto m=load(readhex(folder+"/model"+std::to_string(test)+".hex"));
  auto f=readhex(folder+"/features"+std::to_string(test)+".hex");Features v;
  if(f.size()!=N)throw std::runtime_error("features length");
  for(int i=0;i<N;i++)v[i]=f[i];
  auto expected=readhex(folder+"/query"+std::to_string(test)+".hex");
  auto scores=readhex(folder+"/scores"+std::to_string(test)+".hex");
  for(auto fn:{direct,lookup,fwht}){
   auto r=fn(v,m);
   for(int j=0;j<D;j++)if(((r.q[j/64]>>(j%64))&1)!=expected[j])throw std::runtime_error("query mismatch");
   for(int k=0;k<K;k++)if(r.score[k]!=int(scores[k]))throw std::runtime_error("score mismatch");
  }
 }
 std::cout<<"PASS: all three CPU algorithms match all query bits and class scores for four RTL test cases\n";
 auto model=load(readhex(folder+"/model2.hex"));std::array<Features,64> inputs{};
 std::mt19937 gen(20261112);for(auto& v:inputs)for(auto& x:v)x=gen()%4;
 // Additional random-vector cross-check of exact optimized implementations.
 for(const auto& v:inputs){auto a=direct(v,model),b=lookup(v,model),c=fwht(v,model);
  if(a.q!=b.q || a.q!=c.q || a.score!=b.score || a.score!=c.score)throw std::runtime_error("random mismatch");}
 std::cout<<"PASS: 64 additional random inputs, D=8192 N=196 K=10; warm-cache, model resident\n";
 std::cout<<std::fixed<<std::setprecision(4);
 bench("direct_parity",direct,inputs,model);
 bench("stored_hv_vectorized",lookup,inputs,model);
 bench("exact_fwht",fwht,inputs,model);
 std::array<Image,64> images{};
 for(auto& image:images)for(auto& x:image)x=gen()%256;
 for(auto& kernel:filters)for(auto& w:kernel)w=int(gen()%256)-128;
 for(const auto& image:images)if(convolutional(image)!=convolutional_reference(image))
  throw std::runtime_error("convolution/pooling mismatch");
 std::cout<<"PASS: cropped convolution+pooling matches direct six-loop reference on 64 images\n";
 bench_front("regional_frontend",regional,images,model,false);
 bench_front("convolutional_frontend",convolutional,images,model,false);
 bench_front("regional_plus_fwht",regional,images,model,true);
 bench_front("convolutional_plus_fwht",convolutional,images,model,true);
 std::cout<<"checksum="<<checksum<<"\n";
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
