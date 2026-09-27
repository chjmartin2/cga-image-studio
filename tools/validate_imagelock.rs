//! Executes the unmodified MartyPC core for a full mode-4 palette stream.
//! OUT observations are instruction boundaries, not exact I/O latch clocks.
//! Arguments: workspace COM-or-DSK phase cycles output-directory first-OUT-IP
//!            [expected-320x200-RGBI-index-file]. IP is hexadecimal.
//! For a COM, omitted IP or "auto" reads its descriptor's first visible OUT.
use std::{path::PathBuf, fs, io::{Write,BufWriter}};
use marty_common::types::joystick::ControllerLayout;
use marty_core::{coreconfig::CoreConfig, cpu_common::{Cpu,CpuOption,Register16,Register8,TraceMode},
 cpu_validator::ValidatorType, machine::{MachineBuilder,MachineRomManifest,MachineRomEntry,ExecutionControl,ExecutionState},
 machine_config::{MachineConfiguration,VideoCardConfig,FloppyControllerConfig,FloppyDriveConfig},
 machine_types::{MachineType,OnHaltBehavior,FdcType,FloppyDriveType}, device_traits::videocard::VideoType};
struct Config;
fn image_kernel_offsets(bytes: &[u8])->Option<(u32,u32)> {
 if bytes.get(0xE00..0xE08)? != b"IMGLK001" {return None;}
 let table=u16::from_le_bytes(bytes.get(0xE0A..0xE0C)?.try_into().ok()?) as usize;
 let first=u16::from_le_bytes(bytes.get(table..table+2)?.try_into().ok()?) as usize;
 let end=u16::from_le_bytes(bytes.get(0xE14..0xE16)?.try_into().ok()?) as u32+0x100;
 if first==0 || *bytes.get(first-1)? != 0xB0 || *bytes.get(first+1)? != 0xEE {return None;}
 Some((first as u32+0x101,end))
}
impl CoreConfig for Config {
 fn get_base_dir(&self)->PathBuf { PathBuf::from(".") }
 fn get_machine_type(&self)->MachineType {MachineType::Ibm5160}
 fn get_audio_enabled(&self)->bool {false}
 fn get_machine_noroms(&self)->bool {false}
 fn get_machine_turbo(&self)->bool {false}
 fn get_service_interrupt(&self)->Option<u8> {None}
 fn get_keyboard_layout(&self)->Option<String> {None}
 fn get_keyboard_debug(&self)->bool {false}
 fn get_validator_type(&self)->Option<ValidatorType> {None}
 fn get_validator_trace_file(&self)->Option<PathBuf> {None}
 fn get_validator_baud(&self)->Option<u32> {None}
 fn get_validator_port(&self)->Option<String> {None}
 fn get_cpu_trace_mode(&self)->Option<TraceMode> {None}
 fn get_cpu_dram_refresh_simulation(&self)->bool {true}
 fn get_cpu_trace_on(&self)->bool {false}
 fn get_cpu_trace_file(&self)->Option<PathBuf> {None}
 fn get_title_hacks(&self)->bool {false}
 fn get_patch_enabled(&self)->bool {false}
 fn get_halt_behavior(&self)->OnHaltBehavior {OnHaltBehavior::Continue}
 fn get_terminal_port(&self)->Option<u16> {None}
 fn get_controller_layout(&self)->Option<ControllerLayout> {None}
}
fn main() {
 let args:Vec<_> = std::env::args().collect();
 let root=PathBuf::from(args.get(1).expect("workspace argument"));
 let input=root.join(args.get(2).expect("COM or DSK path"));
 let phase:u32=args.get(3).map(|s|s.parse().unwrap()).unwrap_or(0);
 let max_cycles:u64=args.get(4).map(|s|s.parse().unwrap()).unwrap_or(30_000_000);
 let output_dir=root.join(args.get(5).map(|s|s.as_str()).unwrap_or("external/research/imagelock-validation/waitstates-on")); fs::create_dir_all(&output_dir).unwrap();
 let disk=input.extension().unwrap().to_string_lossy().eq_ignore_ascii_case("dsk");
 let kernel=if disk {None}else{image_kernel_offsets(&fs::read(&input).expect("COM input"))};
 let active_ip=match args.get(6).map(String::as_str) {
  None | Some("auto") => kernel.expect("Automatic first-visible-OUT detection requires an IMGLK001 COM; for a disk supply that COM's first visible OUT IP").0,
  Some(value) => u32::from_str_radix(value.trim_start_matches("0x"),16).expect("first OUT IP must be hexadecimal or auto"),
 };
 if let Some((first,_))=kernel {assert_eq!(active_ip,first,"Activation must use the descriptor's first visible OUT, not a preroll OUT");}
 let expected=args.get(7).map(|p|fs::read(root.join(p)).expect("expected RGBI index file"));
 if let Some(ref pixels)=expected {assert_eq!(pixels.len(),320*200,"Expected one RGBI index byte per 320x200 pixel");assert!(pixels.iter().all(|p|*p<16),"Expected RGBI indices 0..15");}
 let mut mc=MachineConfiguration::default();
 mc.machine_type=MachineType::Ibm5160;
 mc.video=vec![VideoCardConfig{video_type:VideoType::CGA,video_subtype:None,dip_switch:None,monitor_emulation:true}];
 mc.fdc=Some(FloppyControllerConfig{fdc_type:FdcType::IbmNec,drive:vec![FloppyDriveConfig{fd_type:FloppyDriveType::Floppy360K,image:None}]});
 let rom_path=root.join("external/martypc/install/media/roms/GLaBIOS/GLABIOS_0.2.6_8X.ROM");
 let mut manifest=MachineRomManifest::new();
 manifest.roms.push(MachineRomEntry{name:"GLaBIOS 0.2.6 XT".into(),addr:0xFE000,repeat:1,data:fs::read(&rom_path).unwrap(),path:rom_path,..Default::default()});
 let mut machine=MachineBuilder::new().with_core_config(Box::new(&Config)).with_machine_config(&mc).with_roms(manifest).build().unwrap();
 // MachineBuilder leaves this false; the desktop frontend explicitly enables it.
 // Without this, device waits AND effective DMA refresh steals are suppressed.
 machine.cpu_mut().set_option(CpuOption::EnableWaitStates(true));
 assert!(machine.cpu().get_option(CpuOption::EnableWaitStates(false)),"CPU wait states must match the desktop configuration");
 machine.pit_adjust(phase & 3);
 let mut ec=ExecutionControl::new(); ec.set_state(ExecutionState::Running);
 if disk {machine.fdc().as_mut().unwrap().load_image_from(0,fs::read(&input).unwrap(),Some(&input),true).unwrap();}
 else {
  while machine.cpu_cycles()<20_000_000 {machine.run(100_000,&mut ec);}
  let delay:u32=std::env::var("CGA_ENTRY_DELAY_CYCLES").ok().map(|v|v.parse().unwrap()).unwrap_or(0);
  if delay>0 {machine.run(delay,&mut ec);}
  let segment:u16=std::env::var("CGA_LOAD_SEGMENT").ok().map(|v|u16::from_str_radix(v.trim_start_matches("0x"),16).unwrap()).unwrap_or(0x1000);
  machine.load_program(&fs::read(&input).unwrap(),segment,0x100,segment,0x100).unwrap();
  for reg in [Register16::DS,Register16::ES,Register16::SS] {machine.cpu_mut().set_register16(reg,segment);}
  machine.cpu_mut().set_register16(Register16::SP,0xFFFE);
  machine.cpu_mut().set_flags(0x0202);
 }
 let out=output_dir.join(format!("phase{}.csv",phase));
 let mut wr=BufWriter::new(fs::File::create(out).unwrap());
 writeln!(wr,"cpu_cycle,cs,ip,port,value,beam_x_before,beam_y_before,beam_x_after,beam_y_after,frame,scanline,cpu_cycle_before,kernel_active").unwrap();
 let beginning=machine.cpu_cycles(); let mut writes=0u64; let mut samples=0u64; let mut last_frame=0; let mut active=false; let mut frames_saved=0u64; let mut recorded_cpu_options=false; let mut activations=0u64;
 let mut fw=BufWriter::new(fs::File::create(output_dir.join(format!("phase{phase}-frames.csv"))).unwrap());
 writeln!(fw,"frame,cpu_cycle,fnv64,cropped_fnv64,width_dots,height,aperture_x,aperture_y,mismatching_dots,mismatch_x_min,mismatch_y_min,mismatch_x_max,mismatch_y_max,unequal_pixel_pairs").unwrap();
 while machine.cpu_cycles()-beginning < max_cycles {
  let cpu=machine.cpu(); let cs=cpu.get_register16(Register16::CS); let ip=cpu.flat_ip();
  let dx=cpu.get_register16(Register16::DX); let value=cpu.get_register8(Register8::AL);
  let relative_ip=ip.wrapping_sub((cs as u32)*16); let cycle_before=machine.cpu_cycles();
  let op=machine.bus().peek_u8(ip as usize).unwrap();
  let marker = (op==0xEE || op==0xEF) && (dx==0x3D9 || dx==0x3D8);
  let before=if marker {machine.bus().primary_video().unwrap().beam_pos().unwrap()}else{(0,0)};
  machine.run(1,&mut ec);
  if marker {
   let vc=machine.bus().primary_video().unwrap(); let after=vc.beam_pos().unwrap();
   if dx==0x3D9 && relative_ip==active_ip && vc.is_in_graphics_mode() && !active {active=true;last_frame=vc.frame_count();recorded_cpu_options=false;activations+=1;}
   writeln!(wr,"{},{cs:04X},{relative_ip:04X},{dx:04X},{value:02X},{},{},{},{},{},{},{cycle_before},{}",machine.cpu_cycles(),before.0,before.1,after.0,after.1,vc.frame_count(),vc.scanline(),u8::from(active)).unwrap();
   writes+=1;
  }
  samples+=1;
  // Reentry must acquire again before comparing pixels. A DOS text-mode return
  // ends the previous activation; do not count the next acquisition as a raster.
  if active && !machine.bus().primary_video().unwrap().is_in_graphics_mode() {active=false;}
  if active && !recorded_cpu_options {
   let waits=machine.cpu().get_option(CpuOption::EnableWaitStates(false));
   let refresh=machine.cpu().get_option(CpuOption::ScheduleDramRefresh(false,0,0,false));
   assert!(waits && refresh,"Timed kernel requires active CPU waits and a scheduled DRAM refresh");
   let (pit1_reload,pit1_current,pit1_counting,pit1_retrigger,pit1_mode)={
    let pit=machine.bus_mut().pit_mut().as_mut().unwrap();
    let (reload,current,counting)=pit.get_channel_count(1);
    // clean=false reads presentation state without clearing flags or clocking PIT.
    (reload,current,counting,pit.does_channel_retrigger(1),pit.get_string_state(false).c1_channel_mode.to_string())
   };
   assert_eq!(pit1_reload,19,"PIT1 refresh divisor must be restored before visible output");
   assert!(pit1_counting && pit1_retrigger && pit1_mode=="RateGenerator","PIT1 must be actively counting in mode 2 before visible output");
   let raster_end=kernel.map(|(_,end)|end.to_string()).unwrap_or("null".into());
   fs::write(output_dir.join(format!("phase{phase}-cpu-options.json")),format!("{{\"enable_wait_states\":{waits},\"dram_refresh_schedule_enabled_at_first_out\":{refresh},\"pit1_reload_at_first_out\":{pit1_reload},\"pit1_current_at_first_out\":{pit1_current},\"pit1_counting_at_first_out\":{pit1_counting},\"pit1_retrigger_at_first_out\":{pit1_retrigger},\"pit1_mode_at_first_out\":\"{pit1_mode}\",\"first_out_cpu_cycle\":{},\"first_visible_out_ip\":{active_ip},\"raster_end_ip\":{raster_end}}}\n",machine.cpu_cycles())).unwrap();
   recorded_cpu_options=true;
  }
  if active && machine.bus().primary_video().unwrap().is_in_graphics_mode() {
   let vc=machine.bus().primary_video().unwrap(); let frame=vc.frame_count();
   if frame!=last_frame {
    last_frame=frame; let stride=vc.display_extents().row_stride; let mut hash=0xcbf29ce484222325u64;
    for b in vc.display_buf() {hash=(hash^(*b as u64)).wrapping_mul(0x100000001b3);}
    let ap=vc.display_extents().apertures[0]; let mut crop_hash=0xcbf29ce484222325u64;
    let mut cropped=Vec::with_capacity((ap.w*ap.h) as usize); let mut mismatch=0usize; let(mut x0,mut y0,mut x1,mut y1)=(usize::MAX,usize::MAX,0,0); let mut unequal_pairs=0usize;
    for y in 0..ap.h as usize { for x in 0..ap.w as usize {
     let b=vc.display_buf()[(y+ap.y as usize)*stride+x+ap.x as usize]&15;
     cropped.push(b); crop_hash=(crop_hash^(b as u64)).wrapping_mul(0x100000001b3);
     if x%2==1 && cropped[cropped.len()-2]!=b {unequal_pairs+=1;}
     if let Some(ref pixels)=expected {if ap.w!=640 || ap.h!=200 || pixels[y*320+x/2]!=b {mismatch+=1;x0=x0.min(x);y0=y0.min(y);x1=x1.max(x);y1=y1.max(y);}}
    }}
    let mismatches=if expected.is_some(){mismatch.to_string()}else{"not_compared".into()};
    writeln!(fw,"{frame},{},{hash:016X},{crop_hash:016X},{},{},{},{},{mismatches},{x0},{y0},{x1},{y1},{unequal_pairs}",machine.cpu_cycles(),ap.w,ap.h,ap.x,ap.y).unwrap();
    if frames_saved==0 {fs::write(output_dir.join(format!("phase{phase}-first-active.bin")),vc.display_buf()).unwrap();fs::write(output_dir.join(format!("phase{phase}-first-visible.bin")),&cropped).unwrap();}
    fs::write(output_dir.join(format!("phase{phase}-last-visible.bin")),&cropped).unwrap();
    fs::write(output_dir.join(format!("phase{phase}-active-video.txt")),format!("field_w={} field_h={} stride={} mode={:02X} apertures={:?}",vc.display_extents().field_w,vc.display_extents().field_h,stride,vc.display_extents().mode_byte,vc.display_extents().apertures)).unwrap();
    frames_saved+=1;
   }
  }
  if samples % 2_000_000 == 0 {eprintln!("phase {phase}: {} cycles, {writes} observed writes, CS:IP={cs:04X}:{ip:05X}", machine.cpu_cycles()-beginning);}
  if matches!(ec.get_state(),ExecutionState::Halted) {panic!("Machine halted: {:?}",machine.get_error_str());}
 }
 let vc=machine.bus().primary_video().unwrap();
 fs::write(output_dir.join(format!("phase{phase}-frame.bin")),vc.display_buf()).unwrap();
 fs::write(output_dir.join(format!("phase{phase}-video.txt")),format!("field_w={} field_h={} stride={} mode={:02X} apertures={:?}",vc.display_extents().field_w,vc.display_extents().field_h,vc.display_extents().row_stride,vc.display_extents().mode_byte,vc.display_extents().apertures)).unwrap();
 fs::write(output_dir.join(format!("phase{phase}-run-summary.json")),format!("{{\"activations\":{activations},\"visible_frames\":{frames_saved},\"cpu_cycles\":{}}}\n",machine.cpu_cycles()-beginning)).unwrap();
 println!("phase={phase} cycles={} palette_or_mode_writes={writes} active_frames={frames_saved} activations={activations} state={:?} error={:?}",machine.cpu_cycles()-beginning,ec.get_state(),machine.get_error_str());
}






