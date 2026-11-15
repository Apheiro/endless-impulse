#!/usr/bin/env python3
"""Authenticate the current user with host PAM, isolated from Nix libraries.

Run with the host Python. Read one JSON password from stdin; never accept a
password in arguments or environment variables. Only exit status 0 unlocks.
"""
import ctypes as C
import ctypes.util
import json
import os
import pwd
import sys


class Message(C.Structure):
    _fields_ = [("style", C.c_int), ("text", C.c_char_p)]


class Response(C.Structure):
    _fields_ = [("text", C.c_void_p), ("code", C.c_int)]


Callback = C.CFUNCTYPE(C.c_int, C.c_int, C.POINTER(C.POINTER(Message)),
                      C.POINTER(C.POINTER(Response)), C.c_void_p)


class Conversation(C.Structure):
    _fields_ = [("callback", Callback), ("data", C.c_void_p)]


def conversation(password, username, libc):
    """Allocate replies with libc: PAM owns and frees successful replies."""
    libc.calloc.argtypes = [C.c_size_t, C.c_size_t]
    libc.calloc.restype = C.c_void_p
    libc.strdup.argtypes = [C.c_char_p]
    libc.strdup.restype = C.c_void_p
    libc.free.argtypes = [C.c_void_p]

    @Callback
    def respond(count, messages, output, _data):
        if count <= 0 or count > 32:
            return 19  # PAM_CONV_ERR
        replies = C.cast(libc.calloc(count, C.sizeof(Response)), C.POINTER(Response))
        if not replies:
            return 5  # PAM_BUF_ERR
        try:
            for index in range(count):
                style = messages[index].contents.style
                if style in (1, 2):  # ECHO_OFF (password), ECHO_ON (username)
                    replies[index].text = libc.strdup(password if style == 1 else username)
                    if not replies[index].text:
                        raise MemoryError
                elif style not in (3, 4):  # error/info: no reply
                    raise ValueError("Unsupported PAM prompt")
            output[0] = replies
            return 0
        except Exception:
            for index in range(count):
                if replies[index].text:
                    libc.free(replies[index].text)
            libc.free(replies)
            return 19

    return respond


def authenticate(password):
    if not isinstance(password, str) or "\0" in password:
        return 2
    username = pwd.getpwuid(os.getuid()).pw_name.encode()
    pam = C.CDLL(ctypes.util.find_library("pam") or "libpam.so.0")
    libc = C.CDLL(None)
    callback = conversation(password.encode(), username, libc)
    conv = Conversation(callback, None)
    handle = C.c_void_p()
    pam.pam_start.argtypes = [C.c_char_p, C.c_char_p, C.POINTER(Conversation), C.POINTER(C.c_void_p)]
    pam.pam_authenticate.argtypes = [C.c_void_p, C.c_int]
    pam.pam_end.argtypes = [C.c_void_p, C.c_int]
    result = pam.pam_start(b"login", username, C.byref(conv), C.byref(handle))
    if result != 0:
        return 2
    try:
        result = pam.pam_authenticate(handle, 0)
    finally:
        pam.pam_end(handle, result)
    # PAM_AUTH_ERR, PAM_MAXTRIES, PAM_CRED_INSUFFICIENT, PAM_USER_UNKNOWN.
    return 0 if result == 0 else (1 if result in (7, 8, 10, 11) else 2)


def main():
    try:
        return authenticate(json.loads(sys.stdin.readline()))
    except Exception:
        # Do not print input, exceptions or PAM messages containing user data.
        return 2


if __name__ == "__main__":
    sys.exit(main())
