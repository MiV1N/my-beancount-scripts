import re

# import dateparser


def get_eating_account(from_user, description, time=None):
    if time == None or not hasattr(time, 'hour'):
        return 'Expenses:Eating:Others'
    elif time.hour <= 3 or time.hour >= 21:
        return 'Expenses:Eating:Nightingale'
    elif time.hour <= 10:
        return 'Expenses:Eating:Breakfast'
    elif time.hour <= 16:
        return 'Expenses:Eating:Lunch'
    else:
        return 'Expenses:Eating:Supper'


def get_credit_return(from_user, description, time=None):
    for key, value in credit_cards.items():
        if key == from_user:
            return value
    return "Unknown"


public_accounts = [
    'Assets:Company:Alipay:StupidAlipay'
]

credit_cards = {
    '中信银行': 'Liabilities:CreditCard:CITIC',
}

accounts = {
    "余额宝": 'Assets:Company:Alipay:MonetaryFund',
    '余利宝': 'Assets:Bank:MyBank',
    '花呗': 'Liabilities:Company:Huabei',
    '建设银行': 'Liabilities:CreditCard:CCB',
    '零钱': 'Assets:Balances:WeChat',
}

descriptions = {

    # 支付宝
    '亲情卡': 'Expenses:Miscellaneous:Transfer:Heyao',
    '城市通卡|出行|渡口|打车': 'Expenses:Transportation:PublicTransportation',
    '爱车养车|停车': 'Expenses:Transportation:Car',
    '话费充值': 'Expenses:Electronics:PhoneBills',
    '餐饮美食|面|下午茶|饼|咖啡|coffee|小炒|早餐|酱香饼|餐饮|点餐': 'Expenses:Food',  #
    '果仓':'Expenses:Food:Snacks',
    '日用百货|纯水机|超市|便利': 'Expenses:Household',
    "CLOUDCONE":'Expenses:Electronics:Vps',
    'HOTEL|酒店|订房|住宿':'Expenses:Housing:Rent',

    # 招商银行
    '网上国网':'Expenses:Housing:UtilityBills', #水电费
    '转账.*何瑶':'Expenses:Miscellaneous:Transfer:Heyao',
    '取款':"Assets:Cash",

    # wechat
    '\d+币':'Expenses:Entertainment:Game', #游戏币
    '滕王阁':'Expenses:Entertainment', 

    # 特殊分类
    '好运来|农民一站|黄建兴|赵二姐':'Expenses:Food', #好运来:路边肉饼,农民一站:卖菜的,黄建兴|赵二姐:车站鲜肉饼
    '先用后付|琥佳伦园林|漫步云端|陈文泉|任璐|光明':'Expenses:Miscellaneous:Unknown', #无法分类
    
}

anothers = {
    '上海拉扎斯': get_eating_account
}

incomes = {
    # 招商银行
    '工资\s*重庆紫光华山智安科技有限公司':'Income:Salary:UNISINSIGHT',

    #wechat
    '红包|礼金奖励':'Income:Miscellaneous:Gifts:RedBag',
    '群收款':'Income:Miscellaneous:Unknown', #无法分类

}

description_res = dict([(key, re.compile(key)) for key in descriptions])
another_res = dict([(key, re.compile(key)) for key in anothers])
income_res = dict([(key, re.compile(key)) for key in incomes])
