"""LittleFoot VM opcodes — ported from roli_LittleFootRunner.h."""

from enum import IntEnum


class Op(IntEnum):
    """LittleFoot bytecode opcodes with their exact byte values."""

    HALT = 0x00
    JUMP = 0x01  # +int16 offset
    JUMP_IF_TRUE = 0x02  # +int16 offset
    JUMP_IF_FALSE = 0x03  # +int16 offset
    CALL = 0x04  # +int16 offset
    RET_VOID = 0x05  # +int8 num_args
    RET_VALUE = 0x06  # +int8 num_args
    CALL_NATIVE = 0x07  # +int16 function_id
    DROP = 0x08
    DROP_MULTIPLE = 0x09  # +int8 count
    PUSH_MULTIPLE_0 = 0x0A  # +int8 count
    PUSH_0 = 0x0B
    PUSH_1 = 0x0C
    PUSH_8 = 0x0D  # +int8 value
    PUSH_16 = 0x0E  # +int16 value
    PUSH_32 = 0x0F  # +int32 value
    DUP = 0x10
    DUP_OFFSET_01 = 0x11
    DUP_OFFSET_02 = 0x12
    DUP_OFFSET_03 = 0x13
    DUP_OFFSET_04 = 0x14
    DUP_OFFSET_05 = 0x15
    DUP_OFFSET_06 = 0x16
    DUP_OFFSET_07 = 0x17
    DUP_OFFSET = 0x18  # +int8 offset
    DUP_OFFSET_16 = 0x19  # +int16 offset
    DROP_TO_STACK = 0x1A  # +int8 offset
    DROP_TO_STACK_16 = 0x1B  # +int16 offset
    DUP_FROM_GLOBAL = 0x1C  # +int16 index
    DROP_TO_GLOBAL = 0x1D  # +int16 index
    INT32_TO_FLOAT = 0x1E
    FLOAT_TO_INT32 = 0x1F
    ADD_INT32 = 0x20
    ADD_FLOAT = 0x21
    MUL_INT32 = 0x22
    MUL_FLOAT = 0x23
    SUB_INT32 = 0x24
    SUB_FLOAT = 0x25
    DIV_INT32 = 0x26
    DIV_FLOAT = 0x27
    MOD_INT32 = 0x28
    BITWISE_OR = 0x29
    BITWISE_AND = 0x2A
    BITWISE_XOR = 0x2B
    BITWISE_NOT = 0x2C
    BIT_SHIFT_LEFT = 0x2D
    BIT_SHIFT_RIGHT = 0x2E
    LOGICAL_OR = 0x2F
    LOGICAL_AND = 0x30
    LOGICAL_NOT = 0x31
    TEST_ZE_INT32 = 0x32
    TEST_NZ_INT32 = 0x33
    TEST_GT_INT32 = 0x34
    TEST_GE_INT32 = 0x35
    TEST_LT_INT32 = 0x36
    TEST_LE_INT32 = 0x37
    TEST_ZE_FLOAT = 0x38
    TEST_NZ_FLOAT = 0x39
    TEST_GT_FLOAT = 0x3A
    TEST_GE_FLOAT = 0x3B
    TEST_LT_FLOAT = 0x3C
    TEST_LE_FLOAT = 0x3D
    GET_HEAP_BYTE = 0x3E
    GET_HEAP_INT = 0x3F
    GET_HEAP_BITS = 0x40
    SET_HEAP_BYTE = 0x41
    SET_HEAP_INT = 0x42
