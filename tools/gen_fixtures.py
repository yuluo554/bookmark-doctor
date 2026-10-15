"""生成 / 校验合成书签集（data/fixtures/set-1，冻结产物，禁手改）。

纪律（plan/04 §5.1、plan/05 §3、data/README §3、K5/K6）：
- 确定性：自研 splitmix64 RNG、固定 seed、无系统时钟、禁 stdlib random；
  条目/键输出经显式 sort；写盘 UTF-8 字节、LF 行尾；
- URL 全部使用保留域名（*.invalid），零真实站点 URL；反爬场景由 *.mock.invalid
  主机名表达，基准（M4）运行时重写为 loopback（mock 端口不进 fixtures 字节）；
- truth.json 只存"输入与期望"，无任何 observed 类字段；
- manifest.json：三类易错形态覆盖声明（应有/实际覆盖双数登记）+ 生成参数
  （seed、chrome epoch 常量对账）+ 文件 sha256 表；
- ``--check``：重新生成到内存 → 与仓库现有文件逐字节比对，不一致 exit 1。

用法（仓库根运行）：
    PYTHONPATH=src py -X utf8 tools/gen_fixtures.py           # 生成/覆写
    PYTHONPATH=src py -X utf8 tools/gen_fixtures.py --check   # 位级一致性校验
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bookmark_doctor._encoding import ensure_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures" / "set-1"

SEED = 20261015
SCHEMA_TRUTH = "bookmark-doctor.truth/1"
SCHEMA_MANIFEST = "bookmark-doctor.manifest/1"
# Chrome 纪元常量（1601-01-01 UTC 与 Unix 纪元之差，微秒）：显式声明供真值对账
CHROME_EPOCH_DELTA_US = 11644473600000000

# ---------------------------------------------------------------------------
# 植入设计（生成器同时输出书签文件与真值——真值程序化派生，禁手工标注）
# ---------------------------------------------------------------------------

# mock 主机名（*.mock.invalid）→ 基准运行时映射到 mock_site.py 的路径场景
MOCK_HOSTS = {
    "alive-page.mock.invalid": "200",        # 终态 2xx → alive（通用映射）
    "content-page.mock.invalid": "200",      # 重复收藏承载页（同页多 URL 形态）
    "blocked-403.mock.invalid": "403",       # 反爬 403 → review（B1）
    "risk-302.mock.invalid": "302",          # 风控跳转 302 → review（B1）
    "cdn-521.mock.invalid": "521",           # CDN 拦截 521 → review（B1）
    "gone-404.mock.invalid": "404",          # 死链 404 → dead（B3，唯一通用判死证据）
    "gone-404-b.mock.invalid": "404",        # 死链 404 第二样例（缺 add_date 那条挂此主机）
    "gone-410.mock.invalid": "410",          # 死链 410 → dead（B3）
    "unreachable.mock.invalid": "unreachable",  # 网络不可达 → review（B2；mock 为拒绝连接端口）
    "hang.mock.invalid": "hang",             # 挂起超时 → review（B2）
}
# *.invalid 保留域（非 mock 主机）：DNS 必然失败（RFC 2606）→ review(dns_failure 类)，离线可复现
DNS_FAIL_HOSTS = [
    "docs-guide.invalid", "blog-notes.invalid", "wiki-help.invalid",
    "forum-talk.invalid", "tools-box.invalid", "manual-site.invalid",
]

# 唯一内容键：模拟"同一页面被三种 URL 形态收藏"（重复但形态不同 → 应合并）
DUP_VARIANTS = [
    "https://content-page.mock.invalid/posts/{n}?utm_source=share&utm_medium=link",
    "https://content-page.mock.invalid/posts/{n}/?share_token=abc{z}",
    "https://content-page.mock.invalid/posts/{n}#{tag}",
]


class SplitMix64(object):
    """splitmix64（Java 版 Long.hashCode 终混合同款常数），迭代式确定性 RNG。"""

    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def below(self, bound):
        return self.next() % bound

    def pick(self, seq):
        return seq[self.below(len(seq))]


# 确定性语料（固定清单，不依赖 hash 迭代序）
CN_TITLES = [
    "入门指南", "配置手册", "常见问题", "开发笔记", "学习路线", "踩坑记录",
    "接口文档", "部署教程", "性能优化", "源码导读", "工具清单", "速查表",
]
REALISH_INVALID_HOSTS = [
    "docs-guide.invalid", "blog-notes.invalid", "wiki-help.invalid",
    "forum-talk.invalid", "tools-box.invalid", "manual-site.invalid",
]
TAGS = ["reading", "tech", "daily", "ref"]


def _bm_id(source, seq):
    return hashlib.sha1(("%s|%d" % (source, seq)).encode("utf-8")).hexdigest()[:12]


def _escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _netscape_html(folders):
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<!-- This is an automatically generated file. -->",
        "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">",
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for folder_name, items in folders:
        lines.append("    <DT><H3>%s</H3>" % _escape_html(folder_name))
        lines.append("    <DL><p>")
        for it in items:
            if it.get("add_date") is not None:
                lines.append(
                    "        <DT><A HREF=\"%s\" ADD_DATE=\"%d\">%s</A>"
                    % (_escape_html(it["url"]), it["add_date"], _escape_html(it["title"]))
                )
            else:
                lines.append(
                    "        <DT><A HREF=\"%s\">%s</A>"
                    % (_escape_html(it["url"]), _escape_html(it["title"]))
                )
        lines.append("    </DL><p>")
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


def _chrome_json(folders):
    def node(it):
        n = {
            "type": "url",
            "name": it["title"],
            "url": it["url"],
            "id": it["chrome_id"],
        }
        if it.get("add_date") is not None:
            # Netscape 存 epoch 秒；Chrome 存 1601 纪元微秒——同一条目同值换算
            n["date_added"] = str(it["add_date"] * 1000000 + CHROME_EPOCH_DELTA_US)
        else:
            n["date_added"] = "0"
        return n

    roots = {
        "bookmark_bar": {"children": [], "name": "书签栏", "type": "folder"},
        "other": {"children": [], "name": "其他书签", "type": "folder"},
        "synced": {"children": [], "name": "移动设备书签", "type": "folder"},
    }
    for idx, (folder_name, items) in enumerate(folders):
        root_key = ["bookmark_bar", "other", "synced"][idx % 3]
        roots[root_key]["children"].append(
            {
                "type": "folder",
                "name": folder_name,
                "children": [node(it) for it in items],
            }
        )
    return {
        "checksum": None,
        "roots": roots,
        "version": 1,
    }


def build_entries():
    """返回 (folders, truth, expected_count)。文件夹顺序确定性。"""
    rng = SplitMix64(SEED)
    folders = [
        ("反爬场景", []),
        ("死链与不可达", []),
        ("重复收藏", []),
        ("假域（DNS 不可达）", []),
    ]
    seq = 0
    chrome_id = 100
    base_ts = 1500000000  # 固定时间基准（非系统时钟）

    # —— 场景 1：反爬类（403/302/521 → review；200 对照 → alive）——
    for host in ["blocked-403.mock.invalid", "risk-302.mock.invalid",
                 "cdn-521.mock.invalid", "alive-page.mock.invalid"]:
        seq += 1
        chrome_id += 1
        folders[0][1].append({
            "id": None,  # 统一稍后按文件内序派生
            "chrome_id": chrome_id,
            "url": "https://%s/article/%d" % (host, seq),
            "title": "反爬样本-%s" % host.split(".")[0],
            "add_date": base_ts + seq * 86400,
        })

    # —— 场景 2：死链（404/410 → dead）与不可达（unreachable/hang → review）——
    for host in ["gone-404.mock.invalid", "gone-410.mock.invalid",
                 "unreachable.mock.invalid", "hang.mock.invalid"]:
        seq += 1
        chrome_id += 1
        folders[1][1].append({
            "id": None,  # 统一稍后按文件内序派生
            "chrome_id": chrome_id,
            "url": "https://%s/page/%d" % (host, seq),
            "title": "可达性样本-%s" % host.split(".")[0],
            "add_date": base_ts + seq * 86400,
        })
    # 无 add_date 的条目（缺失字段 → null，长期未访问分档应单列"添加时间未知"）
    seq += 1
    chrome_id += 1
    folders[1][1].append({
        "id": None,  # 统一稍后按文件内序派生
        "chrome_id": chrome_id,
        "url": "https://gone-404-b.mock.invalid/no-date",
        "title": "可达性样本-缺时间",
        "add_date": None,
    })

    # —— 场景 3：重复收藏（同页三种 URL 形态：utm / share_token / 尾斜杠+fragment）——
    dup_groups = []
    for n in range(1, 5):
        seq += 1
        chrome_id += 1
        urls = [tpl.format(n=n, z=str(rng.below(10)), tag=rng.pick(TAGS)) for tpl in DUP_VARIANTS]
        members = []
        for u in urls:
            chrome_id += 1
            folders[2][1].append({
                "id": None,  # 统一稍后按文件内序派生
                "chrome_id": chrome_id,
                "url": u,
                "title": "重复收藏-%d" % n,
                "add_date": base_ts + seq * 86400,
            })
            members.append(u)
        dup_groups.append({"expect_merge_to": urls[0], "members": members})

    # —— 场景 4：假域（*.invalid 非 mock 主机 → DNS 必然失败 → review(dns_failure)）——
    for i in range(6):
        seq += 1
        chrome_id += 1
        folders[3][1].append({
            "id": None,  # 统一稍后按文件内序派生
            "chrome_id": chrome_id,
            "url": "https://%s/%s/%d.html" % (
                rng.pick(REALISH_INVALID_HOSTS), rng.pick(TAGS), i),
            "title": "%s%s" % (rng.pick(CN_TITLES), i),
            "add_date": base_ts + seq * 86400,
        })

    # —— 按文件内序统一派生全部 id（单一序，避免多套编号碰撞）——
    flat_seq = 0
    for _, items in folders:
        for it in items:
            flat_seq += 1
            assert it["id"] is None
            it["id"] = _bm_id("html", flat_seq)

    # —— 真值（只存输入与期望；无 observed 类字段）——
    by_host = {}
    for _, items in folders:
        for it in items:
            host = it["url"].split("//", 1)[1].split("/", 1)[0]
            by_host.setdefault(host, []).append(it["id"])
    def members_of(hosts):
        ids = []
        for h in hosts:
            ids.extend(by_host.get(h, []))
        return ids

    # 真值分桶（互斥且全覆盖 27 件；add_date_null 为正交标注）
    review_anti = members_of(["blocked-403.mock.invalid", "risk-302.mock.invalid", "cdn-521.mock.invalid"])
    review_unreach = members_of(["unreachable.mock.invalid", "hang.mock.invalid"])
    review_dns = members_of(DNS_FAIL_HOSTS)
    dead_ids = members_of(["gone-404.mock.invalid", "gone-404-b.mock.invalid", "gone-410.mock.invalid"])
    alive_ids = members_of(["alive-page.mock.invalid", "content-page.mock.invalid"])
    truth = {
        "schema": SCHEMA_TRUTH,
        "seed": SEED,
        "expect": {
            "dead": dead_ids,
            "review": review_anti + review_unreach + review_dns,
            "alive": alive_ids,
            "review_reason_class": {
                "anti_crawl": review_anti,
                "network_unreachable": review_unreach,
                "dns_failure": review_dns,
            },
            "add_date_null": [it["id"] for _, items in folders for it in items if it["add_date"] is None],
            "duplicate_groups": dup_groups,
            "scenario_hosts": {k: by_host[k] for k in sorted(MOCK_HOSTS) if k in by_host},
        },
        "expected_check": {
            "dead": dead_ids,
            "review": review_anti + review_unreach + review_dns,
            "alive": alive_ids,
            "add_date_null": [it["id"] for _, items in folders for it in items if it["add_date"] is None],
        },
    }
    n_items = sum(len(items) for _, items in folders)
    host_counts = {}
    for host, ids in by_host.items():
        host_counts[host] = len(ids)
    return folders, truth, n_items, host_counts


def build_manifest(folders, truth, n_items, host_counts, sha_table):
    # 覆盖声明：三类易错形态（data/README §3.5），应有/实际覆盖双数登记
    dead_n = sum(
        host_counts.get(h, 0)
        for h in ["gone-404.mock.invalid", "gone-404-b.mock.invalid", "gone-410.mock.invalid"]
    )
    dup_n = len(truth["expect"]["duplicate_groups"])
    # covered = 声明主机清单的实算件数（与 expected_check 分桶口径解耦）
    review_anti_crawl_n = sum(
        host_counts.get(h, 0)
        for h in ["blocked-403.mock.invalid", "risk-302.mock.invalid", "cdn-521.mock.invalid"]
    )
    manifest = {
        "schema": SCHEMA_MANIFEST,
        "set_id": "set-1",
        "generator": "tools/gen_fixtures.py",
        "seed": SEED,
        "chrome_epoch_delta_us": CHROME_EPOCH_DELTA_US,
        "counts": {
            "bookmarks": n_items,
            "folders": len(folders),
        },
        "coverage": {
            "sampling_note": "抽样覆盖非穷举：以下为三类易错形态的植入清单与件数（应有/实际覆盖双数登记）",
            "review_not_dead": {
                "should_cover": 3,
                "covered": review_anti_crawl_n,
                "hosts": ["blocked-403.mock.invalid", "risk-302.mock.invalid", "cdn-521.mock.invalid"],
                "detail": "反爬 403/302/521 应落 review，不得误判 dead（B1）",
            },
            "unreachable_not_dead": {
                "should_cover": 2,
                "covered": 2,
                "hosts": ["unreachable.mock.invalid", "hang.mock.invalid"],
                "detail": "网络不可达/超时应落 review，不得误判 dead（B2）",
            },
            "dead_hit": {
                "should_cover": 3,
                "covered": dead_n,
                "hosts": ["gone-404.mock.invalid", "gone-404-b.mock.invalid", "gone-410.mock.invalid"],
                "detail": "404/410 应落 dead（B3，唯一通用判死证据）",
            },
            "duplicate_merge": {
                "should_cover": 4,
                "covered": dup_n,
                "detail": "同页多种 URL 形态应合并（B5）",
            },
        },
        "files": sha_table,
        "mock_host_scenarios": MOCK_HOSTS,
    }
    return manifest


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def build_all():
    folders, truth, n_items, host_counts = build_entries()
    html_bytes = _netscape_html(folders).encode("utf-8")
    chrome_bytes = json.dumps(
        _chrome_json(folders), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    truth_bytes = json.dumps(truth, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"

    files = {
        "bookmarks.netscape.html": _sha256_bytes(html_bytes),
        "bookmarks.chrome.json": _sha256_bytes(chrome_bytes),
        "truth.json": _sha256_bytes(truth_bytes),
    }
    manifest = build_manifest(folders, truth, n_items, host_counts, files)
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    return {
        "bookmarks.netscape.html": html_bytes,
        "bookmarks.chrome.json": chrome_bytes,
        "truth.json": truth_bytes,
        "manifest.json": manifest_bytes,
    }


def main(argv=None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成 / 校验合成书签集 data/fixtures/set-1（冻结产物）")
    parser.add_argument("--check", action="store_true", help="重新生成并与现有文件逐字节比对（不覆写）")
    args = parser.parse_args(argv)

    outputs = build_all()
    if args.check:
        diffs = []
        for name, data in sorted(outputs.items()):
            path = FIXTURES_DIR / name
            if not path.exists():
                diffs.append("缺少 %s" % path)
            elif path.read_bytes() != data:
                diffs.append("位级不一致: %s" % path)
        if diffs:
            for line in diffs:
                print("[gen_fixtures] %s" % line, file=sys.stderr)
            print("[gen_fixtures] --check 失败（禁手改，请整目录重生成）", file=sys.stderr)
            return 1
        print("[gen_fixtures] --check 通过：4 个文件位级一致")
        return 0

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(outputs.items()):
        (FIXTURES_DIR / name).write_bytes(data)
        print("[gen_fixtures] 已写入 %s" % (FIXTURES_DIR / name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
