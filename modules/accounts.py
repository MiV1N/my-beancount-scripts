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


    # ; 服装子分类
    '服饰':'Expenses:Clothing',

    # ; 食物子分类
    '餐饮美食|面|下午茶|蛋糕|食品|饼|小炒|吐司|干锅|早餐|盒马|酱香饼|餐饮|点餐|美团|海底捞|灶东家|餐厅|每味每客|莱得快|乡村基|生鲜|果蔬': 'Expenses:Food',  #
    '果仓|果之缘':'Expenses:Food:Snacks',
    '饮品|咖啡|coffee|Coffee|霸王茶姬|贩卖机':"Expenses:Food:Beverages",

    # ; 住房子分类
    'HOTEL|酒店|订房|住宿':'Expenses:Housing:Rent',
    '物业':'Expenses:Housing',
    '网上国网|水费|电力|电费':'Expenses:Housing:UtilityBills', #水电费
    '宜家|五金|家居家装':'Expenses:Housing:Furniture',


    # ; 交通子分类
    '城市通卡|出行|渡口|打车|中交|T3': 'Expenses:Transportation:PublicTransportation',
    '爱车养车|停车|南网电动|深圳交警|太平财产保险有限公司|石油|特斯拉': 'Expenses:Transportation:Car',

    # ; 用
    '日用百货|纯水机|超市|便利|无印良品|怪兽充电|罗森|美容美发': 'Expenses:Household',


    # ; 通讯子分类
    '话费充值|充值缴费|手机充值|手机壳': 'Expenses:Electronics:PhoneBills',
    "CLOUDCONE|服务器|云服务":'Expenses:Electronics:Vps',

    # ; 娱乐子分类
    '\d+币|游乐|手游|儿童乐园':'Expenses:Entertainment:Game', #游戏币
    '滕王阁|文化休闲':'Expenses:Entertainment', 
    '推拿|按摩':'Expenses:Entertainment:Massage',

    # ; 健康子分类
    '医院|妇幼保健院|医疗健康|药房':"Expenses:Health:MedicalExpenses",

    # ; 教育子分类
    '教育培训':'Expenses:Education',

    # ; 杂项子分类
    '母婴亲子': 'Expenses:Miscellaneous:杨青晓',
    '亲情卡': 'Expenses:Miscellaneous:Transfer:Heyao',
    '转账.*(何)*瑶':'Expenses:Miscellaneous:Transfer:Heyao',
    '转账.*杨平':'Expenses:Miscellaneous:Transfer:Yangping',
    '转账.*唐大秀':'Expenses:Miscellaneous:Transfer:Tangdaxiu',
    
    # 内部转账
    '取款':"Assets:Cash",
    '华智跟投':"Assets:Investments:UNISINSIGHT",
    '朝朝宝':'Assets:Investments:朝朝宝',
    '购买零钱+':'Assets:Investments:CITIC:零钱plus',
    '中信.*信用卡还款':'Liabilities:CreditCard:CITIC:3995',

    # 特殊分类（放最后），最后匹配 
    '好运来|农民一站|黄建兴|赵二姐|果行天下|谭文勇|漫步云端':'Expenses:Food', 
    #好运来:路边肉饼,农民一站:卖菜的,黄建兴|赵二姐:车站鲜肉饼，果行天下:龙德下面的水果摊,谭文勇:龙德门口的肠粉
    #漫步云端: 秦小厨外卖收款
    '段毅':'Expenses:Transportation:Car', #汽车代上牌
    '陈文泉':'Expenses:Food:Snacks', #陈文泉:龙德下面的水果摊,
    

    # 无法分类
    '先用后付|琥佳伦园林|任璐|光明|广州宇凡商业管理有限公司|陈明国|英':'Expenses:Miscellaneous:Unknown', #无法分类
    '微信转账|二维码收款|收钱码收款':'Expenses:Miscellaneous:Unknown', #无法分类
}

anothers = {
    '上海拉扎斯': get_eating_account
}

incomes = {
    # 招商银行
    '工资\s*重庆紫光华山智安科技有限公司|款项.*代发|重庆紫光华山智安科技有限公司.*工资|重庆紫光华山智安科技有限公司.*奖金':'Income:Salary:UNISINSIGHT',
    '重庆紫光华山智安科技有限公司工会委员会|报销.*重庆紫光华山智安':'Income:Miscellaneous:Reimbursement:UNISINSIGHT',
    # '重庆紫光华山智安科技有限公司.*奖金':'Income:Salary:UNISINSIGHT',

    '结息':'Income:Interest',

    #wechat
    '红包|礼金奖励|支付鼓励金|补贴|多多视频|抽奖|返现':'Income:Miscellaneous:Gifts:RedBag',

    '建信人寿保险':'Income:Health:Insurance', #保险赔偿

    '退款|退货':'Income:Miscellaneous:Refund',

    '(汇入汇款|转入).*何瑶':'Income:Miscellaneous:Heyao',
    '汇入汇款.*杨平':'Income:Miscellaneous:Yangping',
    '汇入汇款.*唐大秀':'Income:Miscellaneous:Tangdaxiu',
    
    # 无法分类
    '群收款|微信转账':'Income:Miscellaneous:Unknown', #无法分类


}

description_res = dict([(key, re.compile(key)) for key in descriptions])
another_res = dict([(key, re.compile(key)) for key in anothers])
income_res = dict([(key, re.compile(key)) for key in incomes])
