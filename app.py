import streamlit as st
import re
import json
import requests
from datetime import datetime
import xml.etree.ElementTree as ET

# Configuration de la page
st.set_page_config(
    page_title="XML Auto-Corrector",
    page_icon="🔧",
    layout="wide"
)

def detect_and_decode(file_bytes):
    """Detecte l'encodage et decode le fichier"""
    encodings = ['utf-8', 'utf-8-sig', 'iso-8859-1', 'cp1252', 'latin1']
    
    for encoding in encodings:
        try:
            content = file_bytes.decode(encoding)
            return content, encoding
        except UnicodeDecodeError:
            continue
    
    content = file_bytes.decode('utf-8', errors='replace')
    return content, 'utf-8-with-errors'

def load_corrections():
    """Charge les corrections depuis GitHub"""
    try:
        # URL du fichier corrections.json dans votre repository
        url = "https://raw.githubusercontent.com/younessemalii/xpo-xml-auto-corrector/main/corrections.json"
        response = requests.get(url)
        
        if response.status_code == 200:
            return json.loads(response.text)
        else:
            st.warning("⚠️ Impossible de charger les corrections depuis GitHub")
            return {}
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des corrections: {e}")
        return {}

def extract_order_number(xml_content):
    """Extrait le numero de commande du XML"""
    try:
        # Chercher la balise OrderId avec IdValue
        pattern = r'<OrderId[^>]*>\s*<IdValue>([^<]+)</IdValue>'
        match = re.search(pattern, xml_content, re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        # Alternative: chercher directement IdValue dans OrderId
        root = ET.fromstring(xml_content)
        for order_id in root.iter():
            if 'OrderId' in str(order_id.tag):
                id_value = order_id.find('.//IdValue')
                if id_value is not None and id_value.text:
                    return id_value.text.strip()
        
        return None
    except Exception as e:
        st.error(f"❌ Erreur extraction numero commande: {e}")
        return None

def add_customer_job_code(xml_content, job_code):
    """Ajoute la balise CustomerJobCode apres CostCenterName"""
    try:
        # Pattern pour trouver CostCenterName et ajouter CustomerJobCode juste apres
        pattern = r'(<CostCenterName>[^<]*</CostCenterName>)'
        replacement = f'\\1\n        <CustomerJobCode>{job_code}</CustomerJobCode>'
        
        # Verifier si CustomerJobCode existe deja
        if '<CustomerJobCode>' in xml_content:
            # Remplacer la valeur existante
            xml_content = re.sub(
                r'<CustomerJobCode>[^<]*</CustomerJobCode>',
                f'<CustomerJobCode>{job_code}</CustomerJobCode>',
                xml_content
            )
            return xml_content, "mise_a_jour"
        else:
            # Ajouter la nouvelle balise
            xml_content = re.sub(pattern, replacement, xml_content)
            return xml_content, "ajout"
    
    except Exception as e:
        st.error(f"❌ Erreur ajout CustomerJobCode: {e}")
        return xml_content, "erreur"

def apply_corrections(xml_content, order_number, corrections):
    """Applique les corrections pour une commande donnee"""
    if order_number not in corrections:
        return xml_content, []
    
    order_corrections = corrections[order_number]
    applied_corrections = []
    
    for field, value in order_corrections.items():
        if field == "CustomerJobCode":
            xml_content, status = add_customer_job_code(xml_content, value)
            if status in ["ajout", "mise_a_jour"]:
                applied_corrections.append(f"CustomerJobCode: {value} ({status})")
        # Ici on peut ajouter d'autres types de corrections
    
    return xml_content, applied_corrections

def main():
    """Interface principale"""
    
    # Titre et description
    st.title("🔧 XML Auto-Corrector")
    st.write("Correction automatique des fichiers XML selon les non-conformites PIXID")
    
    # Charger les corrections disponibles
    with st.spinner("🔄 Chargement des corrections depuis GitHub..."):
        corrections = load_corrections()
    
    if corrections:
        st.success(f"✅ {len(corrections)} corrections chargees depuis GitHub")
        
        # Afficher un apercu des corrections disponibles
        with st.expander("📋 Apercu des corrections disponibles"):
            for order_num, order_corrections in list(corrections.items())[:5]:
                st.write(f"**Commande {order_num}:**")
                for field, value in order_corrections.items():
                    st.write(f"  • {field}: `{value}`")
            if len(corrections) > 5:
                st.write(f"... et {len(corrections) - 5} autres commandes")
    else:
        st.info("ℹ️ Aucune correction disponible pour le moment")
    
    st.write("---")
    
    # Upload du fichier XML
    st.header("📁 Upload du fichier XML")
    xml_file = st.file_uploader(
        "Choisissez votre fichier XML a corriger",
        type=['xml'],
        help="Le fichier sera automatiquement corrige selon les donnees de GitHub"
    )
    
    if xml_file is not None:
        # Lire le fichier XML
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
        
        # Extraire le numero de commande
        order_number = extract_order_number(xml_content)
        
        if order_number:
            st.info(f"🏷️ Numero de commande detecte: **{order_number}**")
            
            # Verifier si des corrections existent pour cette commande
            if order_number in corrections:
                st.success(f"✅ Corrections trouvees pour la commande {order_number}")
                
                # Afficher les corrections qui vont etre appliquees
                order_corrections = corrections[order_number]
                st.write("**Corrections a appliquer:**")
                for field, value in order_corrections.items():
                    st.write(f"• **{field}**: `{value}`")
                
                # Bouton pour appliquer les corrections
                if st.button("🔄 Appliquer les corrections", type="primary"):
                    with st.spinner("🔧 Application des corrections..."):
                        corrected_xml, applied_corrections = apply_corrections(
                            xml_content, order_number, corrections
                        )
                    
                    if applied_corrections:
                        st.success("✅ Corrections appliquees avec succes!")
                        
                        # Afficher les corrections appliquees
                        st.write("**Corrections appliquees:**")
                        for correction in applied_corrections:
                            st.write(f"• {correction}")
                        
                        # Bouton de telechargement
                        timestamp = datetime.now().strftime('%H%M%S')
                        filename = f"{xml_file.name.split('.')[0]}_corrected_{timestamp}.xml"
                        
                        # Encoder en ISO-8859-1 pour le telechargement
                        try:
                            xml_bytes = corrected_xml.encode('iso-8859-1', errors='replace')
                        except:
                            xml_bytes = corrected_xml.encode('utf-8', errors='replace')
                        
                        st.download_button(
                            label="📥 Telecharger le XML corrige",
                            data=xml_bytes,
                            file_name=filename,
                            mime="application/xml"
                        )
                    else:
                        st.warning("⚠️ Aucune correction n'a pu etre appliquee")
            
            else:
                st.warning(f"⚠️ Aucune correction trouvee pour la commande **{order_number}**")
                st.info("💡 Verifiez que Make.com a bien traite l'email de non-conformite pour cette commande")
        
        else:
            st.error("❌ Impossible d'extraire le numero de commande du fichier XML")
            st.info("💡 Verifiez que le fichier contient bien une balise `<OrderId><IdValue>XXXXX</IdValue></OrderId>`")
    
    # Informations sur le systeme
    st.write("---")
    st.header("ℹ️ Comment ca marche")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**🔄 Processus automatique:**")
        st.write("1. 📧 Reception email non-conformite")
        st.write("2. 🤖 Make.com analyse l'email")
        st.write("3. 📊 Mise a jour GitHub automatique")
        st.write("4. 🔧 Streamlit applique les corrections")
    
    with col2:
        st.write("**📋 Types de corrections:**")
        st.write("• **CustomerJobCode**: Poste de travail")
        st.write("• **Autres balises**: Selon les besoins")
        st.write("• **Position**: Apres CostCenterName")
        st.write("• **Format**: Extraction intelligente")
    
    # Derniere mise a jour
    if corrections:
        st.write("---")
        st.caption(f"🕒 Dernieres corrections chargees: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
