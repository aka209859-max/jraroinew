"""
集計キーのカテゴリ分類定義（実DB構造対応版）。
各キーは "テーブル名.カラム名" 形式で記述し、
analysis_engine.py が _strip_table_prefix() でカラム名のみ抽出する。

カラム名はデータローダ (data_loader_v2.py) が生成するDataFrameの列名に
完全一致させること。
"""

FACTOR_CATEGORIES: dict = {
    # =========================================================================
    # レース基本条件
    # =========================================================================
    "レース基本条件": {
        "icon": "🏇",
        "factors": [
            {"key": "jvd_se.keibajo_code",          "label": "競馬場",            "desc": "01札幌〜10小倉"},
            {"key": "jrd_bac_fixed.bac_kyori",       "label": "距離",              "desc": "メートル (bac_kyor)"},
            {"key": "jvd_ra.track_code",             "label": "トラック種別",      "desc": "芝/ダート/障害"},
            {"key": "jrd_bac_fixed.shiba_da_shogai_code", "label": "芝ダ障コード", "desc": "芝/ダート/障害区分"},
            {"key": "jrd_bac_fixed.shubetsu",        "label": "競走種別",          "desc": "平地/障害等"},
            {"key": "jrd_bac_fixed.jouken",          "label": "競走条件",          "desc": "新馬/未勝利/1勝等"},
            {"key": "jrd_bac_fixed.juryo_shubetsu_code", "label": "重量種別",      "desc": "馬齢/定量/別定/ハンデ"},
            {"key": "jrd_bac_fixed.grade",           "label": "グレード",          "desc": "G1/G2/G3/OP/L"},
            {"key": "jrd_bac_fixed.course",          "label": "コース",            "desc": "Aコース/Bコース等"},
            {"key": "jrd_bac_fixed.bac_kaisai_kubun","label": "開催区分",          "desc": ""},
            {"key": "jrd_bac_fixed.tosu",            "label": "頭数",              "desc": "出走頭数"},
            {"key": "jrd_bac_fixed.migi_hidari",     "label": "回り",              "desc": "右/左"},
            {"key": "jrd_bac_fixed.uchi_soto",       "label": "内外",              "desc": "内/外"},
        ],
    },
    # =========================================================================
    # 天候・馬場
    # =========================================================================
    "天候・馬場": {
        "icon": "🌤",
        "factors": [
            {"key": "jvd_ra.tenko_code",             "label": "天候",                  "desc": "晴/曇/雨/小雨/雪"},
            {"key": "jvd_ra.babajotai_code_shiba",   "label": "馬場状態（芝）",        "desc": "良/稍重/重/不良"},
            {"key": "jvd_ra.babajotai_code_dirt",    "label": "馬場状態（ダート）",    "desc": "良/稍重/重/不良"},
            {"key": "jrd_kab.babasa_shiba",          "label": "芝馬場差",              "desc": "JRDBコース補正値"},
            {"key": "jrd_kab.babasa_dirt",           "label": "ダート馬場差",          "desc": "JRDBコース補正値"},
            {"key": "jrd_kab.renzoku_nannichime",    "label": "連続何日目",            "desc": "開催連続日数"},
            {"key": "jrd_kab.shiba_shurui",          "label": "芝種類",                "desc": "野芝/洋芝/混合"},
            {"key": "jrd_kab.chukan_kosuiryo",       "label": "中間降水量",            "desc": "前走後の降雨量"},
        ],
    },
    # =========================================================================
    # JRDB前日指数
    # =========================================================================
    "JRDB前日指数": {
        "icon": "📊",
        "factors": [
            {"key": "jrd_kyi_fixed.idm",             "label": "IDM（総合指数）",   "desc": "JRDB独自の総合能力値"},
            {"key": "jrd_kyi_fixed.sogo_shisu",      "label": "総合指数",          "desc": ""},
            {"key": "jrd_kyi_fixed.kishu_shisu",     "label": "騎手指数",          "desc": ""},
            {"key": "jrd_kyi_fixed.chokyo_shisu",    "label": "調教指数",          "desc": ""},
            {"key": "jrd_kyi_fixed.kyusha_shisu",    "label": "厩舎指数",          "desc": ""},
            {"key": "jrd_kyi_fixed.ten_shisu",       "label": "テン指数",          "desc": "スタートダッシュ力"},
            {"key": "jrd_kyi_fixed.pace_shisu",      "label": "ペース指数",        "desc": ""},
            {"key": "jrd_kyi_fixed.agari_shisu",     "label": "上がり指数",        "desc": "終盤の脚力"},
            {"key": "jrd_kyi_fixed.ichi_shisu",      "label": "位置指数",          "desc": ""},
        ],
    },
    # =========================================================================
    # 馬基本情報
    # =========================================================================
    "馬基本情報": {
        "icon": "🐴",
        "factors": [
            {"key": "jvd_se.barei",                  "label": "馬齢",              "desc": "2歳〜"},
            {"key": "jvd_se.seibetsu_code",          "label": "性別",              "desc": "牡/牝/セン"},
            {"key": "jvd_se.futan_juryo",            "label": "斤量",              "desc": "負担重量kg"},
            {"key": "jvd_se.bataiju",                "label": "馬体重",            "desc": "kg"},
            {"key": "jvd_se.zogen_sa",               "label": "馬体重増減",        "desc": "前走比kg (+ = 増)"},
            {"key": "jvd_se.wakuban",                "label": "枠番",              "desc": "1〜8"},
            {"key": "jvd_se.umaban",                 "label": "馬番",              "desc": "1〜18"},
            {"key": "jvd_se.umakigo_code",           "label": "馬記号",            "desc": ""},
            {"key": "jvd_se.blinker_shiyo_kubun",    "label": "ブリンカー（JVD）", "desc": "0=なし/1=あり"},
            {"key": "jrd_kyi_fixed.kyakushitsu",     "label": "脚質（予測）",      "desc": "逃/先/差/追"},
            {"key": "jrd_kyi_fixed.kyori_tekisei",   "label": "距離適性",          "desc": ""},
            {"key": "jrd_kyi_fixed.kyori_tekisei_2", "label": "距離適性2",         "desc": ""},
            {"key": "jrd_kyi_fixed.blinker",         "label": "ブリンカー（JRDB）","desc": "0=なし/1=あり"},
        ],
    },
    # =========================================================================
    # 適性
    # =========================================================================
    "適性": {
        "icon": "🎯",
        "factors": [
            {"key": "jrd_kyi_fixed.shiba_tekisei_code", "label": "芝適性",       "desc": "◎/○/△/×"},
            {"key": "jrd_kyi_fixed.da_tekisei_code",    "label": "ダート適性",   "desc": "◎/○/△/×"},
            {"key": "jrd_kyi_fixed.omo_tekisei_code",   "label": "重馬場適性",   "desc": "◎/○/△/×"},
            {"key": "jrd_kyi_fixed.soho",               "label": "走法",         "desc": ""},
        ],
    },
    # =========================================================================
    # オッズ・人気
    # =========================================================================
    "オッズ・人気": {
        "icon": "💰",
        "factors": [
            {"key": "jvd_se.tansho_odds",            "label": "単勝オッズ",        "desc": "確定単勝オッズ"},
            {"key": "jvd_se.tansho_ninkijun",        "label": "単勝人気",          "desc": "1〜18"},
            {"key": "jrd_joa_fixed.joa_odds_shisu",  "label": "オッズ指数（JOA）", "desc": "JOA基準オッズ指数"},
            {"key": "jrd_tyb.tyb_odds_shisu",        "label": "オッズ指数（直前）","desc": "直前オッズ指数"},
        ],
    },
    # =========================================================================
    # 騎手・調教師
    # =========================================================================
    "騎手・調教師": {
        "icon": "👤",
        "factors": [
            {"key": "jvd_se.kishu_code",             "label": "騎手コード",        "desc": ""},
            {"key": "jvd_se.chokyoshi_code",         "label": "調教師コード",      "desc": ""},
            {"key": "jvd_se.kishu_minarai_code",     "label": "騎手見習い",        "desc": "減量区分"},
            {"key": "jrd_kyi_fixed.kyusha_rank",     "label": "厩舎ランク",        "desc": "JRDB厩舎ランク"},
        ],
    },
    # =========================================================================
    # 調教データ
    # =========================================================================
    "調教データ": {
        "icon": "🏋",
        "factors": [
            {"key": "jrd_kyi_fixed.chokyo_yajirushi_code", "label": "調教矢印",       "desc": "↑↗→↘↓"},
            {"key": "jrd_cyb_fixed.chokyo_hyoka",          "label": "調教評価",       "desc": ""},
            {"key": "jrd_cyb_fixed.chokyo_type",           "label": "調教タイプ",     "desc": ""},
            {"key": "jrd_cyb_fixed.oikiri_shisu",          "label": "追切指数",       "desc": ""},
            {"key": "jrd_cyb_fixed.shiage_shisu",          "label": "仕上指数",       "desc": ""},
            {"key": "jrd_cyb_fixed.chokyo_ryo_hyoka",      "label": "調教量評価",     "desc": ""},
            {"key": "jrd_cyb_fixed.shiage_shisu_henka",    "label": "仕上指数変化",   "desc": ""},
        ],
    },
    # =========================================================================
    # CID・LS指数
    # =========================================================================
    "CID・LS指数": {
        "icon": "🔬",
        "factors": [
            {"key": "jrd_joa_fixed.ls_shisu",        "label": "LS指数",            "desc": ""},
            {"key": "jrd_joa_fixed.ls_hyoka",        "label": "LS評価",            "desc": ""},
        ],
    },
    # =========================================================================
    # 馬体・馬具
    # =========================================================================
    "馬体・馬具": {
        "icon": "🦶",
        "factors": [
            {"key": "jrd_skb.tokki_code",            "label": "特記コード",        "desc": ""},
            {"key": "jrd_skb.bagu_code",             "label": "馬具コード",        "desc": ""},
            {"key": "jrd_skb.skb_sogo",              "label": "総合評価（馬体）",  "desc": ""},
            {"key": "jrd_skb.hidarimae",             "label": "左前蹄",            "desc": ""},
            {"key": "jrd_skb.migimae",               "label": "右前蹄",            "desc": ""},
            {"key": "jrd_skb.hidariushiro",          "label": "左後蹄",            "desc": ""},
            {"key": "jrd_skb.migiushiro",            "label": "右後蹄",            "desc": ""},
            {"key": "jrd_skb.hami",                  "label": "ハミ",              "desc": "馬具"},
            {"key": "jrd_skb.bandage",               "label": "バンテージ",        "desc": "馬具"},
            {"key": "jrd_skb.teitetsu",              "label": "蹄鉄",              "desc": ""},
            {"key": "jrd_skb.hizume_jotai",          "label": "蹄状態",            "desc": ""},
            {"key": "jrd_skb.soe",                   "label": "ソエ",              "desc": ""},
            {"key": "jrd_skb.kotsuryu",              "label": "骨瘤",              "desc": ""},
        ],
    },
    # =========================================================================
    # 直前情報（当日）
    # =========================================================================
    "直前情報（当日）": {
        "icon": "⏰",
        "factors": [
            {"key": "jrd_tyb.tyb_idm",               "label": "IDM（直前）",           "desc": "当日更新値"},
            {"key": "jrd_tyb.tyb_kishu_shisu",       "label": "騎手指数（直前）",      "desc": ""},
            {"key": "jrd_tyb.joho_shisu",            "label": "情報指数",              "desc": ""},
            {"key": "jrd_tyb.paddock_shisu",         "label": "パドック指数",          "desc": ""},
            {"key": "jrd_tyb.tyb_sogo_shisu",        "label": "総合指数（直前）",      "desc": ""},
            {"key": "jrd_tyb.tyb_batai_code",        "label": "馬体コード（直前）",    "desc": ""},
            {"key": "jrd_tyb.tyb_kehai_code",        "label": "気配コード（直前）",    "desc": ""},
            {"key": "jrd_tyb.tyb_odds_fukusho",      "label": "複勝オッズ（直前）",    "desc": ""},
            {"key": "jrd_tyb.odds_shirushi",         "label": "オッズ印",              "desc": ""},
            {"key": "jrd_tyb.paddock_shirushi",      "label": "パドック印",            "desc": ""},
            {"key": "jrd_tyb.chokuzen_sogo_shirushi","label": "直前総合印",            "desc": ""},
        ],
    },
    # =========================================================================
    # 成績データ（確定）
    # =========================================================================
    "成績データ（確定）": {
        "icon": "🏆",
        "factors": [
            {"key": "jrd_sed.sed_idm",               "label": "IDM（確定）",           "desc": "確定後のIDM"},
            {"key": "jrd_sed.soten",                 "label": "素点",                  "desc": ""},
            {"key": "jrd_sed.babasa",                "label": "馬場差",                "desc": "確定馬場差"},
            {"key": "jrd_sed.pace",                  "label": "ペース",                "desc": "S/M/H"},
            {"key": "jrd_sed.deokure",               "label": "出遅れ",                "desc": ""},
            {"key": "jrd_sed.ichidori",              "label": "位置取り",              "desc": ""},
            {"key": "jrd_sed.furi",                  "label": "不利",                  "desc": ""},
            {"key": "jrd_sed.sed_ten_shisu",         "label": "テン指数（確定）",      "desc": ""},
            {"key": "jrd_sed.sed_agari_shisu",       "label": "上がり指数（確定）",    "desc": ""},
            {"key": "jrd_sed.sed_pace_shisu",        "label": "ペース指数（確定）",    "desc": ""},
            {"key": "jrd_sed.race_p_shisu",          "label": "レースP指数",           "desc": ""},
            {"key": "jrd_sed.race_pace",             "label": "レースペース",          "desc": "S/M/H"},
            {"key": "jrd_sed.uma_pace",              "label": "馬ペース",              "desc": ""},
            {"key": "jrd_sed.kyakushitsu_code",      "label": "脚質（確定）",          "desc": "逃/先/差/追"},
            {"key": "jrd_sed.course_dori_code",      "label": "コース取り",            "desc": ""},
            {"key": "jrd_sed.joshodo_code",          "label": "上昇度",                "desc": ""},
            {"key": "jrd_sed.class_code",            "label": "クラス",                "desc": ""},
            {"key": "jrd_sed.sed_batai_code",        "label": "馬体コード（確定）",    "desc": ""},
            {"key": "jrd_sed.sed_kehai_code",        "label": "気配コード（確定）",    "desc": ""},
            {"key": "jrd_sed.zenhan_3f_taimu",       "label": "前半3F",                "desc": "秒"},
            {"key": "jrd_sed.sed_kohan_3f",          "label": "後半3F（確定）",        "desc": "秒"},
            {"key": "jrd_sed.haraimodoshi_tansho",   "label": "払戻金（単勝）",        "desc": "円"},
            {"key": "jrd_sed.haraimodoshi_fukusho",  "label": "払戻金（複勝）",        "desc": "円"},
            {"key": "jrd_sed.sed_bataiju_zogen",     "label": "馬体重増減（確定）",    "desc": "kg"},
            {"key": "jrd_sed.sed_odds_fukusho",      "label": "複勝オッズ（確定）",    "desc": ""},
        ],
    },
    # =========================================================================
    # 過去成績参照
    # =========================================================================
    "過去成績参照": {
        "icon": "📋",
        "factors": [
            {"key": "jrd_kka.jra",                   "label": "JRA総合成績",       "desc": ""},
            {"key": "jrd_kka.koryu",                 "label": "交流成績",          "desc": ""},
            {"key": "jrd_kka.shiba_dirt",            "label": "芝ダート成績",      "desc": ""},
            {"key": "jrd_kka.shiba_dirt_kyori",      "label": "芝ダート距離別",    "desc": ""},
            {"key": "jrd_kka.torakku_kyori",         "label": "トラック距離別",    "desc": ""},
            {"key": "jrd_kka.rotation",              "label": "ローテーション",    "desc": "前走からの間隔"},
            {"key": "jrd_kka.mawari",                "label": "回り別成績",        "desc": "右/左"},
            {"key": "jrd_kka.kishu",                 "label": "騎手別成績",        "desc": ""},
            {"key": "jrd_kka.ryo",                   "label": "良馬場成績",        "desc": ""},
            {"key": "jrd_kka.yayaomo",               "label": "稍重成績",          "desc": ""},
            {"key": "jrd_kka.omo",                   "label": "重馬場成績",        "desc": ""},
            {"key": "jrd_kka.pace_s",                "label": "Sペース成績",       "desc": ""},
            {"key": "jrd_kka.pace_m",                "label": "Mペース成績",       "desc": ""},
            {"key": "jrd_kka.pace_h",                "label": "Hペース成績",       "desc": ""},
            {"key": "jrd_kka.kisetsu",               "label": "季節別成績",        "desc": ""},
            {"key": "jrd_kka.waku",                  "label": "枠番別成績",        "desc": ""},
            {"key": "jrd_kka.kishu_kyori",           "label": "騎手距離別",        "desc": ""},
            {"key": "jrd_kka.kishu_track",           "label": "騎手トラック別",    "desc": ""},
            {"key": "jrd_kka.kishu_chokyoshi",       "label": "騎手調教師別",      "desc": ""},
            {"key": "jrd_kka.kishu_banushi",         "label": "騎手馬主別",        "desc": ""},
            {"key": "jrd_kka.kishu_blinker",         "label": "騎手ブリンカー別",  "desc": ""},
            {"key": "jrd_kka.chokyoshi_banushi",     "label": "調教師馬主別",      "desc": ""},
        ],
    },
    # =========================================================================
    # 血統
    # =========================================================================
    "血統": {
        "icon": "🧬",
        "factors": [
            {"key": "jrd_ukc.bamei_chichi",          "label": "父馬名",            "desc": ""},
            {"key": "jrd_ukc.bamei_haha",            "label": "母馬名",            "desc": ""},
            {"key": "jrd_ukc.bamei_hahachichi",      "label": "母父馬名（BMS）",   "desc": ""},
            {"key": "jrd_ukc.keito_code_chichi",     "label": "父系統コード",      "desc": ""},
            {"key": "jrd_ukc.keito_code_hahachichi", "label": "母父系統コード",    "desc": ""},
            {"key": "jrd_ukc.ukc_moshoku_code",      "label": "毛色コード",        "desc": ""},
        ],
    },
    # =========================================================================
    # JRA-VAN成績
    # =========================================================================
    "JRA-VAN成績": {
        "icon": "📦",
        "factors": [
            {"key": "jvd_se.ijo_kubun_code",         "label": "異常区分",          "desc": "0=正常"},
            {"key": "jvd_se.kakutei_chakujun",       "label": "確定着順",          "desc": ""},
            {"key": "jvd_se.soha_time",              "label": "走破タイム",        "desc": "0.1秒"},
            {"key": "jvd_se.corner_1",               "label": "コーナー1位置",     "desc": ""},
            {"key": "jvd_se.corner_2",               "label": "コーナー2位置",     "desc": ""},
            {"key": "jvd_se.corner_3",               "label": "コーナー3位置",     "desc": ""},
            {"key": "jvd_se.corner_4",               "label": "コーナー4位置",     "desc": ""},
            {"key": "jvd_se.kohan_4f",               "label": "後半4F",            "desc": ""},
            {"key": "jvd_se.kohan_3f",               "label": "後半3F（JVD）",     "desc": ""},
            {"key": "jvd_se.time_sa",                "label": "タイム差",          "desc": ""},
            {"key": "jvd_se.kyakushitsu_hantei",     "label": "脚質判定（JVD）",   "desc": ""},
        ],
    },
}
