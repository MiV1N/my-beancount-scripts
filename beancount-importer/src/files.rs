use std::io::Cursor;
use std::{collections::HashMap, fmt, fs};
// use std::io::{BufRead, BufReader, Read};
use anyhow::{Context, Result as AnyhowResult};
use calamine::{open_workbook_auto, RangeDeserializerBuilder, Reader};
use csv;
use csv::WriterBuilder;
use log::debug;
use log::{error, info, warn};
use regex::Regex;
use std::path::Path;

/// CSV 文件读取器
pub struct CsvReader {
    pub reader: csv::Reader<Cursor<Vec<u8>>>,
    pub headers: csv::StringRecord,
}

impl CsvReader {
    pub fn new(csv_content: &str) -> anyhow::Result<Self> {
        // 将 &str 转换为 Vec<u8>，从而拥有所有权
        let content_bytes = csv_content.as_bytes().to_vec();
        let cursor = Cursor::new(content_bytes);

        let mut rdr = csv::Reader::from_reader(cursor);
        let headers = rdr.headers()?.clone();

        Ok(CsvReader {
            reader: rdr,
            headers,
        })
    }
}

// // impl Decoder for CsvReader {}
// impl RowIterator for CsvReader {
//     fn next_row(&mut self) -> AnyhowResult<HashMap<String, String>> {
//         let mut map = HashMap::new();
//         match self.reader.records().next() {
//             Some(Ok(record)) => {
//                 for (header, value) in self.headers.iter().zip(record.iter()) {
//                     map.insert(header.to_string(), value.to_string());
//                 }
//                 Ok(map)
//             }
//             Some(Err(e)) => Err(e).context("读取CSV记录时出错"),
//             None => Ok(map),
//         }
//     }
// }

// 实现 Iterator trait 以支持 for 循环
impl Iterator for CsvReader {
    type Item = AnyhowResult<HashMap<String, String>>;

    fn next(&mut self) -> Option<Self::Item> {
        match self.reader.records().next() {
            Some(Ok(record)) => {
                let mut map = HashMap::new();
                for (header, value) in self.headers.iter().zip(record.iter()) {
                    map.insert(header.to_string(), value.to_string());
                }
                Some(Ok(map))
            }
            Some(Err(e)) => Some(Err(e).context("读取CSV记录时出错")),
            None => None, // 遇到文件结束时返回 None，避免死循环
        }
    }
}

// 定义一个类型别名，表示预处理器/处理器函数的类型
type PreprocessorFunction = fn(&str) -> String;
type ProcessorFunction = fn(&mut CsvReader) -> anyhow::Result<()>;

// 定义一个结构体来表示每个数据项

pub struct BillProcessRules {
    pub name_match_regex: Regex,
    pub preprocessor: PreprocessorFunction,
    pub processor: ProcessorFunction,
}

impl fmt::Debug for BillProcessRules {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // 为了避免在debug时调用函数，这里只显示函数指针的地址
        write!(
            f,
            "DataItem {{ name_match_regex: {}, preprocessor: {:p}, processor: {:p} }}",
            self.name_match_regex, self.preprocessor as *const (), self.processor as *const ()
        )
    }
}

/// 用于读取指定目录下的所有csv、xls、xlsx文件的类
#[derive(Debug)]
pub struct BillFiles {
    pub file_paths: Vec<String>,
    pub process_rules: Vec<BillProcessRules>,
}

impl BillFiles {
    /// 创建一个新的 FileReader 实例，传入指定目录路径
    pub fn new(dir_path: &str) -> anyhow::Result<Self> {
        let mut file_paths = Vec::new();
        BillFiles::collect_files(dir_path, &mut file_paths)?;

        Ok(BillFiles {
            file_paths,
            process_rules: Vec::new(),
        })
    }

    /// 递归收集指定目录下的所有csv、xls、xlsx文件
    fn collect_files(dir_path: &str, file_paths: &mut Vec<String>) -> Result<(), std::io::Error> {
        let entries = fs::read_dir(dir_path)?;
        for entry in entries {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                BillFiles::collect_files(path.to_str().unwrap(), file_paths)?;
            } else {
                if let Some(ext) = path.extension() {
                    // if ext == "csv" {
                    if ext == "csv" || ext == "xls" || ext == "xlsx" {
                        file_paths.push(path.to_str().unwrap().to_string());
                    }
                }
            }
        }
        // 将包含“中信”或“CMB”名称的文件放到列表最前面

        file_paths.sort_by_key(|file_path| {
            let file_name: String = file_path.to_lowercase();
            if file_name.contains("中信")
                || file_name.contains("cmb")
                || file_name.contains("citic")
            {
                0
            } else {
                1
            }
        });

        Ok(())
    }

    pub fn regist_processor(&mut self, rule: BillProcessRules) -> anyhow::Result<()> {
        self.process_rules.push(rule);
        Ok(())
    }

    pub fn excel_to_csv_string(excel_path: &str) -> anyhow::Result<String> {
        // info!("excel_to_csv_string: {}", file_path);
        // "a,b,c\n1,2,3\n".to_string()
        // 尝试打开 Excel 文件，calamine 会自动检测文件类型
        let mut workbook = open_workbook_auto(excel_path)?;

        let sheet_names = workbook.sheet_names();
        let sheet_name = sheet_names.first().unwrap();

        // 获取第一个工作表的范围
        let range = workbook
            .worksheet_range(sheet_name)
            .expect(format!("无法获取工作表 '{}' 的范围", sheet_name).as_str());

        // 创建一个内存中的 CSV 写入器
        let mut writer = WriterBuilder::new()
            .has_headers(true) // 如果你的 Excel 文件第一行是标题，这里可以设置为 true
            .from_writer(vec![]); // 写入到 Vec<u8> 中

        // 遍历 Excel 范围中的每一行
        for row in range.rows() {
            let mut record: Vec<String> = Vec::new();
            for cell in row {
                // 将每个单元格的值转换为字符串
                record.push(format!("{}", cell).trim().to_string());
            }
            writer.write_record(&record)?; // 写入 CSV 记录
        }

        // 将 Vec<u8> 转换为 String
        let csv_bytes = writer.into_inner()?;
        let csv_string = String::from_utf8(csv_bytes)?;

        Ok(csv_string)
    }

    pub fn process(&self) -> anyhow::Result<()> {
        for file_path in &self.file_paths {
            // 将file_path 与 process_rules 进行匹配，找到对应的处理函数
            for rule in &self.process_rules {
                if rule.name_match_regex.is_match(file_path) {
                    info!("开始处理文件: {},", file_path);
                    let mut content: String = "".to_string();
                    //判断文件是csv还是excel
                    let path: &Path = Path::new(file_path);
                    if let Some(ext) = path.extension().and_then(|s| s.to_str()) {
                        match ext.to_lowercase().as_str() {
                            "csv" => {
                                content = fs::read_to_string(file_path)?;
                            }
                            "xls" => {
                                info!("xls file: {}", file_path);
                                content = Self::excel_to_csv_string(file_path)?;
                            }
                            "xlsx" => {
                                info!("xlsx file: {}", file_path);
                            }
                            _ => {
                                warn!("unsupported file type: {}", ext);
                            }
                        }
                    }

                    // 调用预处理函数处理文件
                    let preprocessed_csv_content = (rule.preprocessor)(&mut content);

                    // 创建CsvReader实例
                    let mut csv_reader: CsvReader = match CsvReader::new(&preprocessed_csv_content)
                    {
                        Ok(reader) => reader,
                        Err(e) => {
                            error!("创建CsvReader失败: {}", e);
                            continue;
                        }
                    };

                    // 调用处理函数处理文件
                    (rule.processor)(&mut csv_reader)?;
                    break;
                }
            }
        }
        Ok(())
    }

    pub fn iter(&self) -> std::slice::Iter<'_, String> {
        self.file_paths.iter()
    }
}

// /// 递归收集指定目录下的所有csv、xls、xlsx文件
// fn collect_files(dir_path: &str, file_paths: &mut Vec<String>) -> Result<(), std::io::Error> {
//     let entries = fs::read_dir(dir_path)?;
//     for entry in entries {
//         let entry = entry?;
//         let path = entry.path();
//         if path.is_dir() {
//             collect_files(path.to_str().unwrap(), file_paths)?;
//         } else {
//             if let Some(ext) = path.extension() {
//                 if ext == "csv" {
//                     // if ext == "csv" || ext == "xls" || ext == "xlsx" {
//                     file_paths.push(path.to_str().unwrap().to_string());
//                 }
//             }
//         }
//     }
//     // 将包含“中信”或“CMB”名称的文件放到列表最前面

//     file_paths.sort_by_key(|file_path| {
//         let file_name: String = file_path.to_lowercase();
//         if file_name.contains("中信") || file_name.contains("cmb") || file_name.contains("citic")
//         {
//             0
//         } else {
//             1
//         }
//     });

//     Ok(())
// }

#[cfg(test)]
mod tests {
    use super::*;
    // use std::fs;
    // use std::path::PathBuf;

    #[test]
    fn test_collect_files() {
        let mut file_paths = Vec::new();
        // 使用测试数据目录
        BillFiles::collect_files("test_datas", &mut file_paths).expect("Failed to collect files");
        assert!(!file_paths.is_empty(), "No files collected");

        // 验证收集到CSV和Excel文件
        let has_csv = file_paths.iter().any(|p| p.ends_with(".csv"));
        let has_excel = file_paths
            .iter()
            .any(|p| p.ends_with(".xls") || p.ends_with(".xlsx"));
        assert!(has_csv, "No CSV files found");
        assert!(has_excel, "No Excel files found");
    }

    // #[test]
    // fn test_file_reader() {
    //     let mut reader = FileReader::new("test_datas").expect("Failed to create FileReader");
    //     let mut line_count = 0;

    //     // 读取至少10行数据验证功能
    //     while let Some(_line) = reader.next_line() {
    //         line_count += 1;
    //         if line_count >= 10 {
    //             break;
    //         }
    //     }

    //     assert!(line_count >= 10, "Not enough lines read from files");
    // }

    #[test]
    fn test_csv_reader() {
        // 测试CSV文件读取
        let csv_path = "test_datas/rust/微信支付账单(20240101-20240228).csv";
        let mut reader = CsvReader::new(csv_path).expect("Failed to create CsvReader");
        let mut line_count = 0;

        // 读取几行数据验证功能
        while let Some(line) = reader.next_row() {
            line_count += 1;
            println!("Line {}: {:#?}", line_count, line);
            // if line_count >= 5 {
            //     break;
            // }
        }

        assert!(line_count >= 5, "Not enough lines read from CSV file");
    }

    // #[test]
    // fn test_detect_encoding() {
    //     // 测试UTF-8编码检测
    //     let utf8_file = fs::File::open("test_datas/微信/微信支付账单(20240101-20240228).csv").unwrap();
    //     let utf8_reader = detect_and_decode(utf8_file);
    //     let mut utf8_content = String::new();
    //     std::io::Read::read_to_string(utf8_reader, &mut utf8_content).unwrap();
    //     assert!(utf8_content.contains("微信支付账单"), "UTF-8 content not decoded correctly");
    // }
}
