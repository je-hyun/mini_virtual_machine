#!/usr/bin/env python3
"""
@author Je Hyun Kim
Implementation of virtual machine for LC-3 assembly language in python

Code is adapted from sources listed in README.md.

I have modified the code to visualize step by step what is going on in the virtual machine, including memory and registers,
for educational purposes. Namely, I created the vsys and parts of operations and traps, as well as the main_generator
method.

License: MIT
"""

__version__ = '1.1'

import array
import select
import sys
import termios
import tty
import getch
from functools import wraps

def instruction_decorator(func):
    @wraps(func)
    def function_wrapper(*args, **kwargs):
        #print(f"Before calling {func.__name__} with arguments {args}")
        func(*args, **kwargs)
    return function_wrapper

UINT16_MAX = 2 ** 16
PC_START = 0x3000

is_running = 1
memory = None

class vsys:
    command_buffer = ""
    @staticmethod
    def stdin():
        return sys.stdin
    class stdout:
        output_buffer = ""
        @staticmethod
        def flush():
            sys.stdout.flush()
            #vsys.stdout.output_buffer = ""
        @staticmethod
        def write(c):
            sys.stdout.write(c)
            vsys.stdout.output_buffer += c
        @staticmethod
        def read(n):
            sys.stdout.read(n)


class R:
    '''
    Enumation for the 10 registers
    R0 - R7   - General Purpose
    PC      - Program Counter
    COND    - Conditional Flag

    The COUNT enum is merely to find the count of registers (10)
    '''
    R0      = 0
    R1      = 1
    R2      = 2
    R3      = 3
    R4      = 4
    R5      = 5
    R6      = 6
    R7      = 7
    PC      = 8
    COND    = 9
    COUNT   = 10


class register_dict(dict):
    '''Creates a dictionary that can only have values between 0 and UINT16_MAX
    This is used to represent registers'''
    def __setitem__(self, key, value):
        super().__setitem__(key, value % UINT16_MAX)


#Initializes registers to 0's
reg = register_dict({i: 0 for i in range(R.COUNT)})

class OP:
    """opcodes.
    There are only 16 opcodes in LC-3, including unused opcode 13.
    """
    BR = 0  # branch
    ADD = 1  # add
    LD = 2  # load
    ST = 3  # store
    JSR = 4  # jump register
    AND = 5  # bitwise and
    LDR = 6  # load register
    STR = 7  # store register
    RTI = 8  # unused
    NOT = 9  # bitwise not
    LDI = 10  # load indirect
    STI = 11  # store indirect
    RET = 12  # jump
    JMP = 12  # jump
    RES = 13  # reserved (unused)
    LEA = 14  # load effective address
    TRAP = 15  # execute trap


class FL:
    """condition flags
    R_COND register stores flags for most recent calculation.

    This is useful for something like if statements.

    e.g.
    AND R0, R0, 0                      ; clear R0
    LOOP                               ; label at the top of our loop
    ADD R0, R0, 1                      ; add 1 to R0 and store back in R0
    ADD R1, R0, -10                    ; subtract 10 from R0 and store back in R1
    BRn LOOP                           ; go back to LOOP if the result was negative (aka check if R0-10 < 0)
    """
    POS = 1 << 0  # P - 1 (<< is bitwise shift left, aka 2^n)
    ZRO = 1 << 1  # Z - 2
    NEG = 1 << 2  # N - 4


"""
OPs implementaion
"""


def bad_opcode(op):
    raise Exception(f'Bad opcode: {op}')

@instruction_decorator
def add(instr):
    # destination register (DR)
    r0 = (instr >> 9) & 0x7
    # first operand (SR1)
    r1 = (instr >> 6) & 0x7
    # whether we are in immediate mode
    imm_flag = (instr >> 5) & 0x1

    if imm_flag:
        imm5 = sign_extend(instr & 0x1F, 5)
        reg[r0] = reg[r1] + imm5
    else:
        r2 = instr & 0x7
        reg[r0] = reg[r1] + reg[r2]

    update_flags(r0)

@instruction_decorator
def ldi(instr):
    """Load indirect"""
    # destination register (DR)
    r0 = (instr >> 9) & 0x7
    # PCoffset 9
    pc_offset = sign_extend(instr & 0x1ff, 9)
    # add pc_offset to the current PC, look at that memory location to get
    # the final address
    reg[r0] = mem_read(mem_read(reg[R.PC] + pc_offset))
    update_flags(r0)

@instruction_decorator
def and_(instr):
    r0 = (instr >> 9) & 0x7
    r1 = (instr >> 6) & 0x7
    r2 = instr & 0x7
    imm_flag = (instr >> 5) & 0x1

    if imm_flag:
        imm5 = sign_extend(instr & 0x1F, 5)
        reg[r0] = reg[r1] & imm5
    else:
        reg[r0] = reg[r1] & reg[r2]

    update_flags(r0)

@instruction_decorator
def not_(instr):
    r0 = (instr >> 9) & 0x7
    r1 = (instr >> 6) & 0x7
    reg[r0] = ~reg[r1]
    update_flags(r0)

@instruction_decorator
def br(instr):
    pc_offset = sign_extend((instr) & 0x1ff, 9)
    cond_flag = (instr >> 9) & 0x7
    if cond_flag & reg[R.COND]:
        reg[R.PC] += pc_offset

@instruction_decorator
def jmp(instr):
    r1 = (instr >> 6) & 0x7
    reg[R.PC] = reg[r1]
    vsys.command_buffer = f"JMP {r1} ; Move the PC"

@instruction_decorator
def jsr(instr):
    r1 = (instr >> 6) & 0x7
    long_pc_offset = sign_extend(instr & 0x7ff, 11)
    long_flag = (instr >> 11) & 1
    reg[R.R7] = reg[R.PC]

    if long_flag:
        reg[R.PC] += long_pc_offset  # JSR
    else:
        reg[R.PC] = reg[r1]

@instruction_decorator
def ld(instr):
    r0 = (instr >> 9) & 0x7
    pc_offset = sign_extend(instr & 0x1ff, 9)
    reg[r0] = mem_read(reg[R.PC] + pc_offset)
    update_flags(r0)

@instruction_decorator
def ldr(instr):
    r0 = (instr >> 9) & 0x7
    r1 = (instr >> 6) & 0x7
    offset = sign_extend(instr & 0x3F, 6)
    reg[r0] = mem_read(reg[r1] + offset)
    update_flags(r0)

@instruction_decorator
def lea(instr):
    r0 = (instr >> 9) & 0x7
    pc_offset = sign_extend(instr & 0x1ff, 9)
    reg[r0] = reg[R.PC] + pc_offset
    update_flags(r0)
    vsys.command_buffer = f"LEA {r0} {reg[r0]} ; Load Effective Address"

@instruction_decorator
def st(instr):
    r0 = (instr >> 9) & 0x7
    pc_offset = sign_extend(instr & 0x1ff, 9)
    mem_write(reg[R.PC] + pc_offset, reg[r0])

@instruction_decorator
def sti(instr):
    r0 = (instr >> 9) & 0x7
    pc_offset = sign_extend(instr & 0x1ff, 9)
    mem_write(mem_read(reg[R.PC] + pc_offset), reg[r0])

@instruction_decorator
def str_(instr):
    r0 = (instr >> 9) & 0x7
    r1 = (instr >> 6) & 0x7
    offset = sign_extend(instr & 0x3F, 6)
    mem_write(reg[r1] + offset, reg[r0])


"""
TRAPs implementation
"""


class Trap:
    GETC = 0x20  # get character from keyboard
    OUT = 0x21  # output a character
    PUTS = 0x22  # output a word string
    IN = 0x23  # input a string
    PUTSP = 0x24  # output a byte string
    HALT = 0x25  # halt the program


def trap(instr):
    traps.get(instr & 0xFF)()


def trap_putc():
    i = reg[R.R0]
    c = memory[i]
    while c != 0:
        vsys.stdout.write(c)
        i += 1
        c = memory[i]


def trap_getc():
    reg[R.R0] = ord(getch.getch())


def trap_out():
    vsys.stdout.write(chr(reg[R.R0]))
    vsys.stdout.flush()
    vsys.command_buffer = f"OUT ({vsys.stdout.output_buffer}) ; output a character"


def trap_in():
    vsys.stdout.write("Enter a character: ")
    vsys.stdout.flush()
    vsys.command_buffer = "IN"
    reg[R.R0] = vsys.stdout.read(1)


def trap_puts():
    for i in range(reg[R.R0], len(memory)):
        c = memory[i]
        if c == 0:
            break
        vsys.stdout.write(chr(c))
    vsys.command_buffer = f"PUTS ; output a byte string ({vsys.stdout.output_buffer})"
    vsys.stdout.flush()





def trap_putsp():
    for i in range(reg[R.R0], len(memory)):
        c = memory[i]
        if c == 0:
            break
        vsys.stdout.write(chr(c & 0xFF))
        char = c >> 8
        if char:
            vsys.stdout.write(chr(char))
    vsys.command_buffer = f"PUTS ; ({vsys.stdout.output_buffer})"
    vsys.stdout.flush()


def trap_halt():
    global is_running
    print('HALT')
    vsys.command_buffer = f"HALT ; end the program"
    is_running = 0


traps = {
    Trap.GETC: trap_getc,
    Trap.OUT: trap_out,
    Trap.PUTS: trap_puts,
    Trap.IN: trap_in,
    Trap.PUTSP: trap_putsp,
    Trap.HALT: trap_halt,
}


ops = {
    OP.ADD: add,
    OP.NOT: not_,
    OP.AND: and_,
    OP.BR: br,
    OP.JMP: jmp,
    OP.RET: jmp,
    OP.JSR: jsr,
    OP.LD: ld,
    OP.LDI: ldi,
    OP.LDR: ldr,
    OP.LEA: lea,
    OP.ST: st,
    OP.STI: sti,
    OP.STR: str_,
    OP.TRAP: trap,
}


class Mr:
    KBSR = 0xFE00  # keyboard status
    KBDR = 0xFE02  # keyboard data


def check_key():
    _, o, _ = select.select([], [vsys.stdin()], [], 0)
    for s in o:
        if s == vsys.stdin():
            return True
    return False


def mem_write(address, val):
    address = address % UINT16_MAX
    memory[address] = val


def mem_read(address):
    address = address % UINT16_MAX
    if address == Mr.KBSR:
        if check_key():
            memory[Mr.KBSR] = 1 << 15
            memory[Mr.KBDR] = ord(getch.getch())
        else:
            memory[Mr.KBSR] = 0
    return memory[address]


def sign_extend(x, bit_count):
    if (x >> (bit_count - 1)) & 1:
        x |= 0xFFFF << bit_count
    return x & 0xffff


def update_flags(r):
    if not reg.get(r):
        reg[R.COND] = FL.ZRO
    elif reg[r] >> 15:
        reg[R.COND] = FL.NEG
    else:
        reg[R.COND] = FL.POS


def read_image_file(file_name):
    global memory

    with open(file_name, 'rb') as f:
        origin = int.from_bytes(f.read(2), byteorder='big')
        memory = array.array("H", [0] * origin)
        max_read = UINT16_MAX - origin
        memory.frombytes(f.read(max_read))
        memory.byteswap()
        memory.fromlist([0]*(UINT16_MAX - len(memory)))


def main(args=sys.argv):
    if len(args) < 2:
        print('vm.py [obj-file]')
        exit(2)

    file_path = args[1]
    read_image_file(file_path)

    reg[R.PC] = PC_START

    while is_running:
        instr = mem_read(reg[R.PC])
        reg[R.PC] += 1
        op = instr >> 12
        fun = ops.get(op, bad_opcode)
        fun(instr)

def main_generator(args=sys.argv):
    '''This is like main, but yields after each instruction, allowing us to use the state of this vm for any
    output visualizer or user interface, e.g. Flask.

    :param args: system arguments, but can be executed outside of command line interface
    :yield: After each instruction yields the program counter
    '''
    global is_running
    is_running = 1
    if len(args) < 2:
        print('vm.py [obj-file]')
        exit(2)

    file_path = args[1]
    read_image_file(file_path)

    reg[R.PC] = PC_START
    yield {"PC":reg[R.PC], "command":".ORIG x3000", "op_name":".ORIG", "memory":memory}
    while is_running:
        instr = mem_read(reg[R.PC])                             # Load instruction from PC register
        reg[R.PC] += 1                                          # Increment the PC register.
        op = instr >> 12                                        #
        fun = ops.get(op, bad_opcode)                           # Look at the opcode to determine which type of instruction it should perform.
        fun(instr)                                              # Perform the instruction using the parameters in the instruction.
        yield {"PC":reg[R.PC], "command":vsys.command_buffer,"op_name":fun.__name__, "op_code":op, "output_buffer":vsys.stdout.output_buffer, "memory":memory}
        vsys.stdout.output_buffer = ""
        vsys.command_buffer= ""



if __name__ == '__main__':
    main()
