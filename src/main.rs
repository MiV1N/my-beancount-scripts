// 由于 `files` 模块未定义，这里暂时注释掉该导入语句，需确保 `files` 模块存在或使用正确的模块名
mod files;
mod logger;
// use beancount_importer::files::CsvReader;
use files::BillFiles;
use log::{debug, error, info, warn};
use logger::init_logger;

pub mod importers;
use importers::{citi, wechat};

fn main() {
    // 初始化日志系统
    if let Err(e) = init_logger("logs/app.log") {
        eprintln!("初始化日志系统失败: {}", e);
        return;
    }

    // 使用测试数据目录
    let billfiles_result = BillFiles::new("test_datas");

    let Ok(mut billfiles) = billfiles_result else {
        error!("初始化BillFiles失败: {}", billfiles_result.unwrap_err());
        return;
    };

    for file in billfiles.iter() {
        info!("发现文件: {}", file);
    }

    // if let Err(e) = billfiles.regist_processor(wechat::get_rule()) {
    //     error!("注册处理器失败: {}", e);
    //     return;
    // }

    if let Err(e) = billfiles.regist_processor(citi::get_rule()) {
        error!("注册处理器失败: {}", e);
        return;
    }

    if let Err(e) = billfiles.process() {
        error!("处理文件失败: {}", e);
        return;
    }

    // println!("billfiles: {:#?}", billfiles);
}
