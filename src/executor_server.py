import cffi
import json

FFI = None
FFILIB = None


def init():
    global FFI, FFILIB

    FFI = cffi.FFI()

    # Init initialize the sandbox environment
    FFI.cdef("""
    int Init(char* i);
    """)

    # Exec runs command inside container runner
    # Remember to free the return char pointer value
    FFI.cdef("""
    char* Exec(char* e);
    """)

    # FileList get the list of files in the file store.
    # Remember to free the 2-d char array `ids` and `names`
    FFI.cdef("""
    size_t FileList(char*** ids, char*** names);
    """)

    # FileAdd adds file to the file store
    # Remember to free the return char pointer value
    FFI.cdef("""
    char* FileAdd(char* content, int contentLen, char* name);
    """)

    # FileGet gets file from file store by id.
    # If the return value is a positive number or zero, the value represents the length of the file.
    # Otherwise, if the return value is negative, the following error occurred:
    #
    # - `-1`: The file does not exist.
    # - `-2`: go-judge internal error.
    #
    # Remember to free `out`.

    FFI.cdef("""
    int FileGet(char* e, char** out);
    """)

    # FileDelete deletes file from file store by id, returns 0 if failed.
    FFI.cdef("""
    int FileDelete(char* e);
    """)

    FFI.cdef("""
    void free(void *ptr);
    """)

    FFILIB = FFI.dlopen("./go-judge.so")


def init_container(conf: dict):
    assert FFILIB is not None

    return FFILIB.Init(json.dumps(conf).encode("utf-8"))


def exec(cmd: dict) -> dict:
    assert FFILIB is not None
    char_pointer = FFILIB.Exec(json.dumps(cmd).encode("utf-8"))
    res = json.loads(FFI.string(char_pointer).decode("utf-8"))
    FFILIB.free(char_pointer)

    return res


def file_get(fileid: str):
    assert FFILIB is not None
    out_ptr = FFI.new("char**", FFI.NULL)
    size = FFILIB.FileGet(fileid.encode("utf-8"), out_ptr)
    if size < 0:
        return size, None

    result_str = FFI.string(out_ptr[0], size).decode("utf-8")
    FFILIB.free(out_ptr[0])
    return None, result_str


def file_delete(fileid: str):
    assert FFILIB is not None

    return FFILIB.FileDelete(fileid.encode("utf-8"))
