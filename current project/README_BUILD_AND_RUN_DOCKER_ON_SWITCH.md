# making Onyx P4RT build and run dockers

create P4RT build docker for Mellanox spectrum switch

## changing dependncies commits
in version_ctrl file add a new version, with all needed repositories commits.

## creating docker images
1. get sx_sdk headers and libs:  
  i. [create minimal sdk container from Spectrum switch](https://wikinox.mellanox.com/display/SW/MLNX-OS+Minimal+SX-SDK+Go+Docker+Application "wikinox") follow steps 1-4.  
  i. on host, run docker container: `docker load <image name>` , `docker run -itd <image name>`  
  i. get container name: `docker ps | grep <image name>`  
  i. copy sdk: `docker cp docker cp <container name>:/sx_sdk/ p4rt-build-docker/p4c_flextrum/`  
  i. kill container: `docker kill <container name>`  
2. run `make save VERSION=<version>`  
  
### instructions for 0.1.14 version:
to fix build failure in p4c stage:   
uncomment /p4c_flextrum/flextrum/backend/json_stage/mlnx.def  

# compiling p4 program
## load build docker image
1) in unix system: `docker load docker load -i mlnx-p4rt-build_<version>.img.tar.gz`
2) start container:  `docker run -d mlnx-p4rt-build <version> --name p4rt-build`
3) access container bash: `docker exec p4rt-build bash`
4) update flextrum git: `cd /flextrum && git pull`

## code p4 and needed init/deinit functions
1) write p4 program in <build container>:/flextrum/p4src/<prog name>.  
	(check mirror as an example.)
2) if needed add sdk calls to: /p4src/<prog name>/usr_src/fx_base_user_init.c
3) `./deploy_p4rt_cli_pi.sh [-R flag to only recompile src c files] <prog name>`  
4) copy compilation output - directly from container `scp /flextrum/output/<prog name>.tar.gz <temp path>`  
	or from host: `docker cp <container id>:/flextrum/output/<prog name>.tar.gz .`


# executing P4 program on Spectrum switch with Onyx NOS
## copy runtime image to switch
```
ssh admin@<Onyx switch ip>
enable
configure terminal
docker no shutdown
image fetch scp://user@host:/<WORKDIR>/mlnx-p4rt-run_0.1.14.img.tar.gz
docker label log
docker load mlnx-p4rt-run_0.1.14.img.tar.gz
```
## running p4rt docker on switch
```
docker start mlnx-p4rt-run 0.1.14 p4rt-run now privileged network sdk label log
docker exec p4rt-run bash
```


## runing p4rt cli
In onyx runtime docker:
```
cd /
scp user@server:/<path to tar p4 compilation output> .
./load_p4rt_pi_cli.sh <p4_prog>	
./pi_CLI_mlnx [-c /<p4_prog>/<p4_prog>.json]
[or: add_p4 /<p4_prog>/<p4_prog>.json]
assign_device 0 0
update_device_start 0 /<p4_prog>/<p4_prog>.bin
update_device_end
```

# TODOs
1.	solve in backend/runtime/spectrum_flexonly/pi_<counter,act_profile>.cpp : app object dependency in member profile.
2.	Untie dependency of flextrum/backend/runtime in flextrum_types.h
3.	Fix range match in CLI (open feature in p4lang/PI repo)
4.	Share objects with onyx
5.	Check salvo.cpp 269 – rc is used uninitialized in this function
6.	Install scp on runtime docker: (apt-get update && apt-get -y install openssh-client)
7.	Gdb to runtime docker
