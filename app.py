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

@st.cache_data(ttl=300)  # Cache pendant 5 minutes
def load_corrections():
    """Charge les corrections depuis GitHub avec cache"""
    try:
        # URL corrigée du fichier corrections.json
        url = "https://raw.githubusercontent.com/younessemlali/xpo-xml-auto-corrector/main/corrections.json"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            corrections = json.loads(response.text)
            # Normaliser les clés pour s'assurer qu'elles ont des zéros de tête
            normalized_corrections = {}
            for order_id, data in corrections.items():
                # Normaliser la clé (ajouter des zéros si nécessaire)
                if order_id and order_id.isdigit() and len(order_id) < 6:
                    normalized_key = order_id.zfill(6)
                else:
                    normalized_key = order_id
                normalized_corrections[normalized_key] = data
            return normalized_corrections
        else:
            st.error(f"❌ Erreur GitHub: {response.status_code}")
            return {}
    except Exception as e:
        st.error(f"❌ Erreur de connexion: {str(e)}")
        return {}

def extract_all_order_numbers(xml_content):
    """Extrait TOUS les numéros de commande du XML (support multi-contrats)"""
    order_numbers = []
    
    try:
        # Méthode 1: Regex pour chercher toutes les balises OrderId avec IdValue
        pattern = r'<OrderId[^>]*>\s*<IdValue>([^<]+)</IdValue>'
        matches = re.findall(pattern, xml_content, re.IGNORECASE)
        
        for match in matches:
            order_id = match.strip()
            # Normaliser avec des zéros de tête si nécessaire
            if order_id.isdigit() and len(order_id) < 6:
                order_id = order_id.zfill(6)
            if order_id not in order_numbers:
                order_numbers.append(order_id)
        
        # Méthode 2: XML parsing comme fallback
        if not order_numbers:
            try:
                root = ET.fromstring(xml_content)
                for order_id_elem in root.iter():
                    if 'OrderId' in str(order_id_elem.tag):
                        id_value = order_id_elem.find('.//IdValue')
                        if id_value is not None and id_value.text:
                            order_id = id_value.text.strip()
                            # Normaliser avec des zéros de tête si nécessaire
                            if order_id.isdigit() and len(order_id) < 6:
                                order_id = order_id.zfill(6)
                            if order_id not in order_numbers:
                                order_numbers.append(order_id)
            except ET.ParseError:
                pass
        
        return order_numbers
    except Exception:
        return []

def add_customer_job_code(xml_content, job_code):
    """Ajoute la balise CustomerJobCode après CostCenterName"""
    try:
        # Vérifier si CustomerJobCode existe déjà
        if '<CustomerJobCode>' in xml_content:
            # Remplacer la valeur existante
            xml_content = re.sub(
                r'<CustomerJobCode>[^<]*</CustomerJobCode>',
                f'<CustomerJobCode>{job_code}</CustomerJobCode>',
                xml_content
            )
            return xml_content, "mise_a_jour"
        else:
            # Pattern pour trouver CostCenterName et ajouter CustomerJobCode juste après
            pattern = r'(<CostCenterName>[^<]*</CostCenterName>)'
            replacement = f'\\1\n        <CustomerJobCode>{job_code}</CustomerJobCode>'
            
            # Compter les occurrences pour s'assurer qu'on fait la substitution
            matches = re.findall(pattern, xml_content)
            if matches:
                xml_content = re.sub(pattern, replacement, xml_content)
                return xml_content, "ajout"
            else:
                # Si CostCenterName n'est pas trouvé, essayer d'autres emplacements
                # Chercher après <OrderId>...</OrderId>
                order_pattern = r'(<OrderId[^>]*>.*?</OrderId>)'
                if re.search(order_pattern, xml_content, re.DOTALL):
                    order_replacement = f'\\1\n        <CustomerJobCode>{job_code}</CustomerJobCode>'
                    xml_content = re.sub(order_pattern, order_replacement, xml_content, flags=re.DOTALL)
                    return xml_content, "ajout_alternatif"
                else:
                    return xml_content, "emplacement_non_trouve"
    
    except Exception as e:
        return xml_content, f"erreur: {str(e)}"

def apply_corrections_to_xml(xml_content, order_numbers, corrections):
    """Applique les corrections pour toutes les commandes détectées"""
    all_applied_corrections = []
    corrected_xml = xml_content
    
    for order_number in order_numbers:
        if order_number in corrections:
            order_corrections = corrections[order_number]
            
            for field, value in order_corrections.items():
                if field == "CustomerJobCode":
                    corrected_xml, status = add_customer_job_code(corrected_xml, value)
                    if status in ["ajout", "mise_a_jour", "ajout_alternatif"]:
                        all_applied_corrections.append(
                            f"Commande {order_number} - CustomerJobCode: {value} ({status.replace('_', ' ')})"
                        )
                    else:
                        all_applied_corrections.append(
                            f"Commande {order_number} - CustomerJobCode: ÉCHEC ({status})"
                        )
                # Ici on peut ajouter d'autres types de corrections
    
    return corrected_xml, all_applied_corrections

def main():
    """Interface principale"""
    
    # Titre et description
    st.title("🔧 XML Auto-Corrector XPO")
    st.write("Correction automatique des fichiers XML selon les non-conformités PIXID")
    
    # Charger les corrections disponibles
    with st.spinner("🔄 Chargement des corrections depuis GitHub..."):
        corrections = load_corrections()
    
    if corrections:
        st.success(f"✅ {len(corrections)} corrections disponibles")
        
        # Afficher un aperçu des corrections disponibles
        with st.expander("📋 Aperçu des corrections disponibles"):
            for order_num, order_corrections in list(corrections.items())[:5]:
                st.write(f"**Commande {order_num}:**")
                for field, value in order_corrections.items():
                    st.write(f"  • {field}: `{value}`")
            if len(corrections) > 5:
                st.write(f"... et {len(corrections) - 5} autres commandes")
    else:
        st.warning("⚠️ Aucune correction disponible pour le moment")
        st.info("💡 Vérifiez la connexion à GitHub ou attendez que de nouvelles corrections soient ajoutées")
    
    st.write("---")
    
    # Upload du fichier XML
    st.header("📁 Upload du fichier XML")
    xml_file = st.file_uploader(
        "Choisissez votre fichier XML à corriger",
        type=['xml'],
        help="Le fichier sera automatiquement corrigé selon les données disponibles. Support multi-contrats."
    )
    
    if xml_file is not None:
        # Lire le fichier XML
        xml_content, xml_encoding = detect_and_decode(xml_file.read())
        st.success(f"✅ XML lu avec l'encodage: {xml_encoding}")
        
        # Extraire TOUS les numéros de commande
        order_numbers = extract_all_order_numbers(xml_content)
        
        if order_numbers:
            st.info(f"🏷️ Numéro(s) de commande détecté(s): **{', '.join(order_numbers)}**")
            
            # Vérifier quelles commandes ont des corrections disponibles
            available_corrections = {}
            missing_corrections = []
            
            for order_number in order_numbers:
                if order_number in corrections:
                    available_corrections[order_number] = corrections[order_number]
                else:
                    missing_corrections.append(order_number)
            
            if available_corrections:
                st.success(f"✅ Corrections trouvées pour {len(available_corrections)} commande(s)")
                
                # Afficher les corrections qui vont être appliquées
                st.write("**Corrections à appliquer:**")
                for order_num, order_corrections in available_corrections.items():
                    st.write(f"📋 **Commande {order_num}:**")
                    for field, value in order_corrections.items():
                        st.write(f"  • **{field}**: `{value}`")
                
                # Bouton pour appliquer les corrections
                if st.button("🔄 Appliquer les corrections", type="primary"):
                    with st.spinner("🔧 Application des corrections..."):
                        corrected_xml, applied_corrections = apply_corrections_to_xml(
                            xml_content, order_numbers, corrections
                        )
                    
                    if applied_corrections:
                        st.success("✅ Corrections appliquées avec succès!")
                        
                        # Afficher les corrections appliquées
                        st.write("**Corrections appliquées:**")
                        for correction in applied_corrections:
                            if "ÉCHEC" in correction:
                                st.error(f"❌ {correction}")
                            else:
                                st.write(f"✅ {correction}")
                        
                        # Bouton de téléchargement
                        timestamp = datetime.now().strftime('%H%M%S')
                        filename = f"{xml_file.name.split('.')[0]}_corrected_{timestamp}.xml"
                        
                        # Encoder en ISO-8859-1 pour le téléchargement
                        try:
                            xml_bytes = corrected_xml.encode('iso-8859-1', errors='replace')
                        except:
                            xml_bytes = corrected_xml.encode('utf-8', errors='replace')
                        
                        st.download_button(
                            label="📥 Télécharger le XML corrigé",
                            data=xml_bytes,
                            file_name=filename,
                            mime="application/xml"
                        )
                    else:
                        st.warning("⚠️ Aucune correction n'a pu être appliquée")
            
            if missing_corrections:
                st.warning(f"⚠️ Aucune correction trouvée pour: **{', '.join(missing_corrections)}**")
                st.info("💡 Ces commandes ne nécessitent peut-être pas de correction ou seront ajoutées ultérieurement")
        
        else:
            st.error("❌ Impossible d'extraire le numéro de commande du fichier XML")
            st.info("💡 Vérifiez que le fichier contient bien une balise OrderId avec IdValue")
            
            # Afficher un aperçu du XML pour debug
            with st.expander("🔍 Aperçu du contenu XML (pour debug)"):
                st.text(xml_content[:1000] + "..." if len(xml_content) > 1000 else xml_content)
    
    # Informations sur le système
    st.write("---")
    st.header("ℹ️ Comment ça marche")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**🔄 Processus automatique:**")
        st.write("1. 📧 Réception email non-conformité")
        st.write("2. 🤖 Extraction automatique Google Sheets")
        st.write("3. 🔄 Synchronisation GitHub toutes les 15min")
        st.write("4. 🔧 Correction XML instantanée")
        st.write("5. 📥 Téléchargement fichier corrigé")
    
    with col2:
        st.write("**📋 Fonctionnalités:**")
        st.write("• **Multi-contrats**: Support plusieurs commandes/XML")
        st.write("• **Auto-sync**: Données mises à jour automatiquement")
        st.write("• **Zéros préservés**: Format 000721, 001043...")
        st.write("• **Cache intelligent**: Performance optimisée")
        st.write("• **Robuste**: Gestion d'erreurs avancée")
    
    # Statut du système
    st.write("---")
    st.header("📊 Statut du système")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if corrections:
            st.metric("🗂️ Corrections", len(corrections))
        else:
            st.metric("🗂️ Corrections", "0", "❌")
    
    with col2:
        # Afficher l'heure de dernière mise à jour
        current_time = datetime.now().strftime('%H:%M:%S')
        st.metric("🕒 Dernière vérification", current_time)
    
    with col3:
        # Bouton pour forcer le rechargement
        if st.button("🔄 Recharger corrections"):
            st.cache_data.clear()
            st.rerun()
    
    # Dernière mise à jour
    if corrections:
        st.write("---")
        st.caption(f"🔗 Source: GitHub - younessemlali/xpo-xml-auto-corrector")
        st.caption(f"🕒 Cache: 5 minutes | Sync auto: 15 minutes")

if __name__ == "__main__":
    main()
