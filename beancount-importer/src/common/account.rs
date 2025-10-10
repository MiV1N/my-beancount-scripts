use regex::Regex;

pub struct Description {
    pub regex: Regex,
    pub account: PreprocessorFunction,
}

pub static DESCRIPTIONS: Vec<Description> = vec![
    Description {
        regex: Regex::new("服饰").unwrap(),
        account: "Expenses:Clothing",
    },

    // 食物子分类
    Description {
        regex: Regex::new("餐饮美食|面|下午茶|蛋糕|食品|饼|小炒|吐司|干锅|早餐|盒马|酱香饼|餐饮|点餐|美团|海底捞|灶东家|餐厅|每味每客|莱得快|乡村基|生鲜|果蔬").unwrap(),
        account: "Expenses:Food",
    },
    Description {
        regex: Regex::new("果仓|果之缘").unwrap(),
        account: "Expenses:Food:Snacks",
    },
    Description {
        regex: Regex::new("饮品|咖啡|coffee|Coffee|霸王茶姬|贩卖机").unwrap(),
        account: "Expenses:Food:Beverages",
    },
];
