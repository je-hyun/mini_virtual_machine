from app.main import bp
from flask import Flask, render_template, request, flash, redirect, url_for
import disassembler
import glob
import vm
import sys


@bp.route('/', methods=['GET','POST'])
def index():
    obj_list = glob.glob("./obj/*.obj")


    h = disassembler.read_file("./obj/hello.obj")

    for index,inst in enumerate(h):
        pc = index + 1 + 3000
        print(disassembler.single_ins(pc, inst))

    return render_template("main_page.html", obj_list=obj_list)

@bp.route('/view_disassembled/<path:path>', methods=['GET','POST'])
def view_disassembled(path):
    vm_gen = vm.main_generator(args=[sys.argv[0], path])
    commands = [c for c in vm_gen]

    return render_template("disassembler.html", commands=commands)