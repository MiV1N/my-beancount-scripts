import argparse
import re
from datetime import datetime

from pathlib import Path
from beancount import loader
from beancount.core import data
from beancount.parser import parser, printer

from modules.imports.alipay import Alipay
from modules.imports.cmb import CMB
# from modules.imports.abc_credit import ABCCredit
# from modules.imports.ccb_credit import CCBCredit
# from modules.imports.citic_credit import CITICCredit
from modules.imports.citic import CITICC
# from modules.imports.cmb_credit import CMBCredit
# from modules.imports.cmbc_credit import CMBCCredit
# from modules.imports.icbc_credit import ICBCCredit
# from modules.imports.icbc_debit import ICBCDebit
from modules.imports.wechat import WeChat
import logging

logging.basicConfig(level=logging.ERROR)

# from modules.imports.yuebao import YuEBao
# from modules.imports.alipay_prove import AlipayProve

parser = argparse.ArgumentParser("import")
parser.add_argument("--path", help="CSV Path")
parser.add_argument("--entry", help="Entry bean path (default = main.bean)", default='')
parser.add_argument("--out", help="Output bean path", default='')
args = parser.parse_args()

entries = None
if args.entry != '':
    entries, errors, option_map = loader.load_file(args.entry)  #手动记录部分

# importers = [Alipay, AlipayProve, YuEBao, WeChat,
#              ABCCredit, CCBCredit, CITICCredit, CMBCCredit, CMBCredit, ICBCCredit,
#              ICBCDebit]
importers = [Alipay,CMB,WeChat,CITICC]


all_path = Path(args.path)
files = list(all_path.rglob("*.csv"))
files.extend(list(all_path.rglob("*.xls")))

new_entries = entries if entries != None and len(entries)>0 else []

# 文件解析
for file in files:
    logging.debug(f"处理文件：{file.name}")
    instance = None
    for importer in importers:
        try:
            with open(file, 'rb') as f:
                file_bytes = f.read()
                instance = importer(file, file_bytes, new_entries, option_map)
            
            _entries = instance.parse()
            new_entries.extend(_entries)

            break
        except Exception as e:
            logging.debug(e)
            pass

save_name = args.out
if save_name == "":
    now = datetime.now()
    save_name = f'{all_path.absolute()}/{now.strftime("%Y%m%d")}.bean'

with open(save_name, 'w', encoding='utf-8') as f:
    printer.print_entries(new_entries, file=f)

print('Outputed to ' + save_name)
exit(0)

file = parser.parse_one('''
2018-01-15 * "测试" "测试"
	Assets:Test 300 CNY
	Income:Test

''')
print(file.postings)


file.postings[0] = file.postings[0]._replace(
    units=file.postings[0].units._replace(number=100))
print(file.postings[0])

data = printer.format_entry(file)
print(data)
