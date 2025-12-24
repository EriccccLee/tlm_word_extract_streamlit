import streamlit as st
import pandas as pd
import re
import io

st.set_page_config(page_title="단어집 추출 도구", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="stSidebarNav"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_data(file):
    try:
        return pd.read_excel(file, engine='calamine')
    except:
        return pd.read_excel(file)

def has_hangeul(text):
    if not isinstance(text, str): return False
    return bool(re.search('[가-힣]', text))

def has_eng(text):
    if not isinstance(text, str): return False
    return bool(re.search('[a-zA-Z]', text))

def is_sentence(text):
    if any(text.endswith(p) for p in ['.', '!', '?', '니다', '시오', '해요', '세요']):
        return True
    if len(text.split()) > 4: return True
    return False

def clean_term(text):
    text = re.sub(r'\[[A-Fa-f0-9]{6}\]|\[-\]', '', text)
    text = text.strip(' \t\n\r-•*·"\'')
    return text

def process_excel(df, input_version):
    df = df.drop_duplicates()
    df = df.dropna()
    if 'Status' in df.columns:
        df = df[df['Status'] == 'Translated']
    
    version_filtered_df = df[df['Ver'].astype(str).str.contains(str(input_version), na=False)]

    if version_filtered_df.empty:
        return None, "NO_VERSION_MATCH"
    
    proper_noun_pairs = set()
    bracket_pattern = re.compile(r'\[([^\]]+)\]')

    for _, row in version_filtered_df.iterrows():
        txt = str(row.get('Text', ''))
        tra = str(row.get('TransText', ''))
        b_txt = bracket_pattern.findall(txt)
        b_tra = bracket_pattern.findall(tra)
        
        clean_b_txt = [b for b in b_txt if not re.match(r'^[0-9A-Fa-f]{6}$|^-$', b)]
        clean_b_tra = [b for b in b_tra if not re.match(r'^[0-9A-Fa-f]{6}$|^-$', b)]
        
        if len(clean_b_txt) == len(clean_b_tra) and len(clean_b_txt) > 0:
            for t, tr in zip(clean_b_txt, clean_b_tra):
                if has_hangeul(t) and not has_eng(t):
                    proper_noun_pairs.add((t.strip(), tr.strip()))
        
        c_txt = clean_term(txt)
        c_tra = clean_term(tra)
        
        if has_hangeul(c_txt) and 0 < len(c_txt) < 25 and not has_eng(c_txt):
            if not is_sentence(c_txt):
                if not re.match(r'^\d+\s*[가-힣]+$', c_txt):
                    proper_noun_pairs.add((c_txt, c_tra))

    if not proper_noun_pairs:
        return None, "NO_TERMS_FOUND"

    result_df = pd.DataFrame(list(proper_noun_pairs), columns=['Original_KO', 'Translated_CN'])
    result_df = result_df.drop_duplicates().sort_values(by='Original_KO')
    
    result_df['Original_KO'] = result_df['Original_KO'].astype(str)
    result_df = result_df[~result_df['Original_KO'].str.contains(r'\{|%|<|>|~|:|\.\.|…|\?', na=False)]
    
    result_df['len_x'] = result_df['Original_KO'].str.len()
    result_df = result_df[result_df['len_x'] != 1]
    result_df = result_df.sort_values(by=['len_x'], ascending=True)
    result_df.drop(['len_x'], axis=1, inplace=True)
    
    return result_df, "SUCCESS"

# --- 메인 UI ---
st.title("📄 TLM 버전별 단어집 추출기")
st.markdown("---")

st.subheader("1. 파일 업로드")
uploaded_file = st.file_uploader("TLM 엑셀 파일을 선택하세요 (xlsx)", type=['xlsx'])

if uploaded_file:
    if 'last_uploaded_file_id' not in st.session_state:
        st.session_state['last_uploaded_file_id'] = None

    if st.session_state['last_uploaded_file_id'] != uploaded_file.file_id:
        st.session_state['last_uploaded_file_id'] = uploaded_file.file_id
        load_data.clear() 
        
    
    status_placeholder = st.empty()
    
    status_placeholder.info("📂 엑셀 파일을 읽는 중... (약 10~20초 소요)")
    df_raw = load_data(uploaded_file)
    
    status_placeholder.info("🔍 컬럼 유효성 검사 중...")
    if 'Ver' not in df_raw.columns:
        status_placeholder.error("❌ 오류 발생: 업로드된 파일에 'Ver' 컬럼이 없습니다.")
        st.stop() # 이후 로직 실행 중단
    
    status_placeholder.success("✅ 준비 완료!")

    
    with st.expander("🔍 디버깅 정보: 'Ver' 컬럼 데이터 확인"):
        try:
            
            debug_df = df_raw.copy()
            debug_df = debug_df.drop_duplicates()
            debug_df = debug_df.dropna()
            if 'Status' in debug_df.columns:
                debug_df = debug_df[debug_df['Status'] == 'Translated']
            
            unique_vers = debug_df['Ver'].dropna().astype(str).unique()
            
            st.write("아래는 'Status'가 'Translated'이고 행에 빈 셀이 없는 데이터 중에서 발견된 고유 버전 목록입니다. 여기에 없는 버전은 추출 대상에 포함되지 않습니다.")
            st.dataframe(unique_vers, width='stretch')
        except Exception as e:
            st.error(f"'Ver' 컬럼 분석 중 오류가 발생했습니다: {e}")

    st.markdown("---")
    
    
    st.subheader("2. 버전 입력 및 추출")
    input_version = st.text_input("타겟 버전을 입력하세요 (예: 2.300)", placeholder="버전 입력...")
    
    if st.button("글로서리 추출 시작", type="primary"):
        if not input_version:
            st.warning("버전을 입력해야 추출을 시작할 수 있습니다.")
        else:
            with st.spinner(f"버전 {input_version} 데이터를 분석하여 단어쌍을 추출하고 있습니다..."):
                final_df, status = process_excel(df_raw, input_version)

                if status == "SUCCESS":
                    st.success(f"추출 완료! 총 {len(final_df)}개의 단어쌍 발견")
                    st.dataframe(final_df, width='stretch')
                    
                    try:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            final_df.to_excel(writer, index=False, sheet_name='Sheet1')
                        
                        output.seek(0)
                        
                        st.download_button(
                            label="📥 추출 결과 Excel 다운로드",
                            data=output,
                            file_name=f"단어집추출결과_{input_version}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    except ImportError:
                        st.error("Excel 파일 생성을 위해 'xlsxwriter' 라이브러리가 필요합니다. `pip install xlsxwriter` 명령어로 설치한 후 다시 시도해 주세요.")
                
                elif status == "NO_VERSION_MATCH":
                    st.error(f"'{input_version}' 버전을 포함하고 'Status'가 'Translated'인 행을 찾을 수 없습니다. 디버깅 정보의 버전을 다시 확인해주세요.")
                
                elif status == "NO_TERMS_FOUND":
                    st.warning(f"'{input_version}' 버전의 데이터는 찾았으나, 추출 조건(예: 문장이 아닌 짧은 한글 단어)에 맞는 용어를 발견하지 못했습니다.")