/* Regression: native guest reservation on 39-bit VA devices (Fold4/Adreno 730,
 * "native guest reservation failed ... errno 17 (File exists)"). Synthetic
 * fixture only: no game bytes, device or original code. The scenarios mirror
 * plat_reserve_guest (pinned Android host layer, engine/ports/letsgo-android/
 * host.patch): exact half-open range with MAP_FIXED_NOREPLACE; an occupied
 * range fails with EEXIST and is never replaced.
 *
 * Address scenarios need plain mappings of the real window addresses, so they
 * run outside sanitizers (ASan's shadow reservation owns those addresses). */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "adapters/title_adapter.h"
#include "runtime/aot_cpu.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#if defined(__SANITIZE_ADDRESS__) || defined(__SANITIZE_THREAD__) || \
    (defined(__has_feature) && (__has_feature(address_sanitizer) || __has_feature(thread_sanitizer)))
#define ADDRESS_SCENARIOS 0
#else
#define ADDRESS_SCENARIOS 1
#endif

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

static unsigned checks;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"check line%d: %s\n",__LINE__,#x);exit(1);}}while(0)
static const uint8_t contract[32]={0x71,0x22,0x33,0x44};

static NativeManifest fixture(enum TitleId id){
 const TitleAdapter*a=title_adapter_find(id);NativeManifest m={.struct_size=sizeof m,.version=NATIVE_MANIFEST_VERSION,.title_id=id,.program_id=a->program_id,.module_count=a->module_count,.mapping_alignment=16384,.identity={.struct_size=sizeof(ModuleAbiIdentity),.abi_version=MODULE_ABI_VERSION,.target=MODULE_ABI_TARGET_ANDROID_ARM64_LP64,.cpu_identity=MODULE_ABI_CPU_A64_SHARED_66560,.cpu_size=sizeof(Cpu),.cpu_alignment=_Alignof(Cpu),.guest_shift=a->guest_shift,.guest_window_lo=a->canonical_window_lo-a->guest_shift,.guest_window_hi=a->canonical_window_hi-a->guest_shift}};
 memcpy(m.contract_sha256,contract,32);
 for(unsigned i=0;i<a->module_count;i++){NativeModuleSpec *s=&m.modules[i];*s=(NativeModuleSpec){.struct_size=sizeof *s,.module_id=a->modules[i].module_id,.canonical_base=a->modules[i].canonical_base,.mapped_size=0x8000,.text_size=0x4000};s->nso_build_id[31]=0xf1;s->nso_sha256[0]=(uint8_t)(i+1);}
 memcpy(m.modules[0].nso_build_id,a->main_build_prefix,a->main_build_prefix_size);return m;
}

static void build_layout(enum TitleId id,const TitleAdapter*a,SessionLayout*out){
 NativeManifest m=fixture(id);
 CHECK(m.identity.guest_shift==a->guest_shift);
 CHECK(m.identity.guest_window_lo==a->canonical_window_lo-a->guest_shift);
 CHECK(m.identity.guest_window_hi==a->canonical_window_hi-a->guest_shift);
 SessionLayoutSpec spec;TitleAdapterFailure f;
 CHECK(title_adapter_build_native_layout(id,&m,contract,16384,&spec,&f)==TITLE_ADAPTER_OK);
 CHECK(session_layout_build(&spec,out,NULL)==SESSION_LAYOUT_OK);
}

static void logic_tests(enum TitleId id){
 const TitleAdapter*a=title_adapter_find(id);SessionLayout layout;
 build_layout(id,a,&layout);
 CHECK(layout.window.lo==a->canonical_window_lo-a->guest_shift);
 CHECK(layout.window.hi==a->canonical_window_hi-a->guest_shift);
 CHECK(layout.window.hi-layout.window.lo==a->canonical_window_hi-a->canonical_window_lo);
 /* The device runs a 39-bit VA space: the whole guest window must fit. */
 CHECK(layout.window.hi<=(UINT64_C(1)<<39));
 uint64_t actual=0,canonical=0;
 CHECK(session_layout_to_actual(&layout,a->canonical_window_lo,0x1000,&actual));
 CHECK(actual==layout.window.lo);
 CHECK(session_layout_to_canonical(&layout,layout.window.hi-0x1000,0x1000,&canonical));
 CHECK(canonical==a->canonical_window_hi-0x1000);
 printf("logic title=%s window=[0x%llx,0x%llx) canonical=[0x%llx,0x%llx) shift=0x%llx\n",
   (id==TITLE_LAS?"las":"eevee"),(unsigned long long)layout.window.lo,(unsigned long long)layout.window.hi,
   (unsigned long long)a->canonical_window_lo,(unsigned long long)a->canonical_window_hi,
   (unsigned long long)a->guest_shift);
}

#if ADDRESS_SCENARIOS
/* plat_reserve_guest semantics: exact range, MAP_FIXED_NOREPLACE, never replaces. */
static void *reserve_like_plat(uint64_t lo,uint64_t hi){
 return mmap((void*)(uintptr_t)lo,(size_t)(hi-lo),PROT_READ|PROT_WRITE,
   MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE|MAP_FIXED_NOREPLACE,-1,0);
}
static void *simulate_process_mapping(uint64_t lo,size_t size){
 return mmap((void*)(uintptr_t)lo,size,PROT_READ|PROT_WRITE,
   MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
}
static void stamp(unsigned char*p,size_t size,unsigned char seed){
 for(size_t i=0;i<size;i++)p[i]=(unsigned char)(seed+(unsigned)i*7);
}
static int intact(const unsigned char*p,size_t size,unsigned char seed){
 for(size_t i=0;i<size;i++)if(p[i]!=(unsigned char)(seed+(unsigned)i*7))return 0;
 return 1;
}
static void reservation_tests(enum TitleId id){
 const TitleAdapter*a=title_adapter_find(id);SessionLayout layout;
 build_layout(id,a,&layout);
 long page=sysconf(_SC_PAGESIZE);
 CHECK(page>=4096&&(page&(page-1))==0);
 /* Fold4-style collision: a process mapping already sits inside the canonical
  * window when the reservation runs (errno 17 / EEXIST on the historical run). */
 uint64_t sim_lo=a->canonical_window_lo+UINT64_C(0x180000000);
 size_t sim_size=2*(size_t)page;
 CHECK(sim_lo+sim_size<=a->canonical_window_hi);
 void *sim=simulate_process_mapping(sim_lo,sim_size);
 CHECK(sim==(void*)(uintptr_t)sim_lo);
 stamp((unsigned char*)sim,sim_size,0x5a);
 printf("collision title=%s window=[0x%llx,0x%llx) occupied=[0x%llx,0x%llx)\n",
   (id==TITLE_LAS?"las":"eevee"),(unsigned long long)layout.window.lo,(unsigned long long)layout.window.hi,
   (unsigned long long)sim_lo,(unsigned long long)(sim_lo+sim_size));
 /* The strategy must choose a free range: the effective window stays clear of
  * the occupied canonical space and reserves there without clobbering it. */
 CHECK(layout.window.hi<=sim_lo||layout.window.lo>=sim_lo+sim_size);
 errno=0;
 void *reserved=reserve_like_plat(layout.window.lo,layout.window.hi);
 if(reserved==MAP_FAILED)
   fprintf(stderr,"reservation failed window=[0x%llx,0x%llx) errno=%d (%s)\n",
     (unsigned long long)layout.window.lo,(unsigned long long)layout.window.hi,errno,strerror(errno));
 CHECK(reserved==(void*)(uintptr_t)layout.window.lo);
 unsigned char*window=(unsigned char*)reserved;
 size_t window_size=(size_t)(layout.window.hi-layout.window.lo);
 stamp(window+0x1000,(size_t)page,0x11);
 stamp(window+window_size-(size_t)page,(size_t)page,0x22);
 CHECK(intact(window+0x1000,(size_t)page,0x11));
 CHECK(intact(window+window_size-(size_t)page,(size_t)page,0x22));
 CHECK(intact((unsigned char*)sim,sim_size,0x5a));
 CHECK(munmap(reserved,window_size)==0);
 CHECK(intact((unsigned char*)sim,sim_size,0x5a));
 CHECK(munmap(sim,sim_size)==0);
 /* No-clobber proof: an occupied range inside the effective window must make
  * the exact reservation fail cleanly and leave the mapping untouched. */
 uint64_t sim2_lo=layout.window.lo+UINT64_C(0x80000000);
 CHECK(sim2_lo+sim_size<=layout.window.hi);
 void *sim2=simulate_process_mapping(sim2_lo,sim_size);
 CHECK(sim2==(void*)(uintptr_t)sim2_lo);
 stamp((unsigned char*)sim2,sim_size,0xa5);
 errno=0;
 void *attempt=reserve_like_plat(layout.window.lo,layout.window.hi);
 CHECK(attempt==MAP_FAILED);
 CHECK(errno==EEXIST);
 CHECK(intact((unsigned char*)sim2,sim_size,0xa5));
 CHECK(munmap(sim2,sim_size)==0);
}
#endif

int main(int argc,char**argv){
 if(argc!=2)return 2;
 enum TitleId id=!strcmp(argv[1],"las")?TITLE_LAS:!strcmp(argv[1],"eevee")?TITLE_EEVEE:(enum TitleId)99;
 if((int)id==99)return 2;
 logic_tests(id);
#if ADDRESS_SCENARIOS
 reservation_tests(id);
 printf("state=passed title=%s checks=%u scenarios=logic+addresses\n",argv[1],checks);
#else
 printf("state=passed title=%s checks=%u scenarios=logic addresses=not-executed (sanitizer shadow owns fixed addresses)\n",argv[1],checks);
#endif
 return 0;
}
