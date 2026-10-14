all:
	gcc -c test.c
	gcc -nostdlib -no-pie -Wl,-e,foo test.o -o test.elf

check:
	../build/bin/asmc --function foo --harness harness.c test.elf --beautify