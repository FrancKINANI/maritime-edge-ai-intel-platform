
Délais de Publication des Données SAR Global Fishing Watch
Selon la documentation technique de Global Fishing Watch, le délai typique documenté pour le dataset des détections de navires par radar à synthèse d'ouverture (SAR), généralement identifié sous l'ID public-global-sar-presence:latest, est de 5 jours
.
Voici les précisions chiffrées mentionnées dans les sources :
Délai de publication standard : La documentation indique de manière récurrente que les détections de navires industriels sont disponibles de 2017 jusqu'à il y a 5 jours (5 days ago)
.
Délai pour les données dynamiques : Un document spécifique sur la disponibilité des données mentionne un délai de 72 heures (3 jours) pour les données SAR consultables via la carte et les API
.
Fréquence de mise à jour : La mise à jour du dataset est dépendante du passage du satellite (missions Copernicus Sentinel-1 de l'ESA)
.
Comparaison avec les infrastructures : Il ne faut pas confondre ce dataset avec celui des détections d'infrastructures fixes offshore (plateformes pétrolières, éoliennes), dont le délai est nettement plus long, environ 3 mois avant la date actuelle
.
En résumé, si vous recherchez des détections de navires, le chiffre précis à retenir selon la documentation technique principale est un délai de 5 jours

D'après la documentation technique de Global Fishing Watch, la couverture du dataset public-global-sar-vessel-detections (identifié par l'ID public-global-sar-presence:latest) n'est pas uniforme et présente des lacunes géographiques et temporelles documentées.
Voici les précisions concernant la continuité et la couverture géographique :
Continuité temporelle et lacunes
Période de disponibilité : Les données sont disponibles de 2017 jusqu'à il y a 5 jours
.
Variation de la couverture spatiale : La documentation précise que la couverture spatiale varie au fil du temps
.
Impact technique (2021) : Jusqu'en décembre 2021, les données provenaient de deux satellites (Sentinel-1A et Sentinel-1B), permettant une cartographie mondiale des eaux côtières environ tous les six jours
. Depuis l'arrêt de Sentinel-1B en décembre 2021, seul Sentinel-1A est utilisé, ce qui affecte la fréquence de passage (cycle de répétition de 12 jours par satellite)
.
Lacunes géographiques documentées
Le dataset présente des exclusions spécifiques pour limiter les erreurs de détection (faux positifs) :
Zones de haute mer : Le radar Sentinel-1 ne scanne pas la majeure partie de l'océan ouvert (open ocean)
. La mission se concentre prioritairement sur les zones où l'activité industrielle est la plus dense.
Proximité des côtes : Aucune détection n'est fournie à moins de 1 km des côtes pour éviter les confusions avec les rochers ou les anomalies dues à la ligne de rivage
.
Régions polaires : Global Fishing Watch ne classifie pas les objets dans une grande partie de l'Arctique et de l'Antarctique, car la glace de mer génère trop de faux positifs
.
Infrastructures fixes : Les navires détectés sont filtrés pour exclure les infrastructures fixes offshore
.
Couverture géographique annoncée
La couverture est officiellement décrite comme suit :
Type de couverture : Elle est limitée aux "zones de couverture satellite" (satellite coverage areas)
.
Étendue précise : Elle vise une cartographie mondiale des eaux côtières
.
Inégalité géographique : La documentation souligne que toutes les zones ne sont pas couvertes de manière égale ; le nombre d'images par emplacement dépend des priorités de la mission de l'Agence spatiale européenne (ESA), de la latitude et du chevauchement des passages satellites
.
En résumé, bien que qualifié de "mondial" dans certains titres, le dataset est en réalité une cartographie mondiale des zones côtières dépendante des orbites des satellites Sentinel-1, avec des exclusions strictes pour la haute mer, les zones glacées et la bande immédiate des 1 km de rivage

Le dataset SAR Vessel Detections ne repose pas sur le traitement de toutes les scènes Sentinel-1 qui pourraient théoriquement être acquises à l'échelle du globe, car le satellite lui-même ne balaie pas l'intégralité de la surface terrestre de manière uniforme
.
Voici les précisions sur la sélection et les limites de couverture selon les sources :
Absence de couverture en haute mer : Les données SAR de Sentinel-1 ne sont pas échantillonnées sur la majeure partie de l'océan ouvert (open ocean)
. Global Fishing Watch précise que la mission se concentre sur les zones où l'activité industrielle est la plus dense, c'est-à-dire principalement à proximité des côtes
.
Détermination par les priorités de mission : L'étendue et la fréquence des acquisitions d'images dépendent des priorités de la mission de l'Agence spatiale européenne (ESA), ainsi que de la latitude et du chevauchement des passages satellites
.
Exclusions géographiques volontaires : Même lorsqu'une image est disponible, certains sous-ensembles sont exclus du traitement pour garantir la qualité des données :
Proximité des côtes : Aucun objet n'est classifié à moins de 1 km du rivage en raison des ambiguïtés liées à la ligne de côte et aux rochers
.
Zones polaires : Une grande partie de l'Arctique et de l'Antarctique n'est pas traitée car la glace de mer génère trop de faux positifs
.
Fréquence temporelle : La couverture a varié dans le temps. Jusqu'en décembre 2021, l'utilisation de deux satellites (S1A et S1B) permettait une cartographie mondiale des eaux côtières environ tous les six jours. Depuis la fin de mission de S1B, seul S1A est utilisé, ce qui affecte la répétitivité des passages
.
En résumé, le dataset est une sélection dictée par les capacités d'échantillonnage réelles du satellite (orientées vers les côtes par l'ESA) et des filtres méthodologiques appliqués par Global Fishing Watch pour limiter les erreurs de détection dans les zones complexes (glace, rivage)

D'après la documentation disponible, il n'existe pas de mécanisme documenté permettant de demander un traitement à la demande (on-demand processing) de nouvelles images satellite Sentinel-1 pour des zones ou des dates qui ne figurent pas déjà dans le dataset SAR Vessel Detections
.
Voici les précisions importantes concernant les demandes personnalisées et les limites de couverture :
1. Analyse de zones personnalisées vs traitement à la demande
Il est important de distinguer la capacité d'analyser une zone spécifique de la demande de traitement de nouvelles données brutes :
Analyse de zones personnalisées : Vous pouvez tout à fait soumettre des requêtes pour des zones géographiques précises (via un polygone personnalisé ou un objet GeoJSON) en utilisant l'API 4Wings Report ou l'API Bulk Download
. Cependant, ces outils ne font qu'extraire et agréger des données déjà traitées par le pipeline de Global Fishing Watch
.
Traitement de nouvelles données : Le dataset SAR repose sur le traitement automatisé des images acquises selon les priorités de mission de l'Agence spatiale européenne (ESA)
. Global Fishing Watch traite ces images de manière systématique pour les zones côtières mondiales, mais ne mentionne aucune procédure permettant à un utilisateur de déclencher manuellement le traitement d'une scène Sentinel-1 spécifique qui aurait été ignorée par leur pipeline standard
.
2. Mécanisme de suggestion et de retour d'expérience
Bien qu'il n'y ait pas de bouton "traiter cette image", la documentation invite les utilisateurs à interagir avec l'équipe technique pour influencer les développements futurs :
Priorisation : Global Fishing Watch précise que si un utilisateur a besoin de données spécifiques ou souhaite qu'une extension du dataset soit priorisée, il est encouragé à les contacter directement à l'adresse apis@globalfishingwatch.org
.
Amélioration du modèle : Les utilisateurs sont également invités à fournir des retours sur les lacunes de détection ou les erreurs de classification afin d'aider à améliorer les versions futures du modèle de détection
.
3. Rappel des limites de couverture par défaut
La documentation rappelle que le manque de données dans certaines zones est souvent structurel :
Haute mer : Le radar Sentinel-1 n'échantillonne pas la majeure partie de l'océan ouvert
.
Zones exclues : Les détections sont volontairement filtrées à moins d'un kilomètre des côtes et dans les zones de glace de mer (Arctique/Antarctique) pour limiter les faux positifs
.
En résumé, vous pouvez définir vos propres zones d'intérêt pour interroger le dataset existant, mais pour toute donnée manquante hors couverture standard, la seule voie documentée est de soumettre une suggestion par email à l'équipe de Global Fishing Watch pour une éventuelle prise en compte dans les mises à jour globales du dataset

Les différences entre les jeux de données SAR Vessel Detections (Détections de navires par radar) et AIS Vessel Presence (Présence de navires via AIS) de Global Fishing Watch reposent principalement sur la source des données, l'objectif de surveillance et la couverture géographique.
Voici une comparaison détaillée basée sur la documentation technique :
1. Source et Nature des Données
SAR Vessel Detections : Ce dataset utilise des images radar à synthèse d'ouverture provenant de la mission Copernicus Sentinel-1 de l'Agence spatiale européenne (ESA)
. Le radar émet des impulsions micro-ondes et mesure l'énergie renvoyée ("backscatter") pour identifier les objets métalliques en mer, quelles que soient les conditions météorologiques ou la luminosité
.
AIS Vessel Presence : Ce dataset est dérivé des signaux AIS (Automatic Identification System) transmis volontairement par les navires équipés de transpondeurs
. Ces signaux sont collectés par des constellations de satellites et des récepteurs terrestres
.
2. Objectif Principal et "Vaisseaux Sombres"
SAR : Son atout majeur est la détection des "vaisseaux sombres" (dark vessels), c'est-à-dire des navires industriels qui n'ont pas de transpondeur AIS ou qui l'ont délibérément éteint pour éviter d'être suivis
. Environ 75 % des navires de pêche industrielle ne seraient pas suivis par les systèmes publics comme l'AIS
.
AIS Presence : Il vise à offrir une vue d'ensemble de la présence mondiale des navires de tous types (pêche, cargo, pétrolier, etc.) qui utilisent l'AIS
. Contrairement au dataset sur l'effort de pêche, celui-ci se concentre sur la position géographique brute sans classifier l'activité de pêche
.
3. Couverture et Disponibilité
Couverture Géographique : Le SAR est limité aux zones balayées par les satellites Sentinel-1, principalement les eaux côtières, et ne couvre pas la majeure partie de la haute mer
. L'AIS Presence offre une couverture mondiale, limitée uniquement par la portée de réception des signaux AIS
.
Historique et Délai : Les données SAR remontent à 2017 avec un délai de publication d'environ 5 jours
. L'AIS Presence remonte à 2012 avec un délai plus court d'environ 96 heures (4 jours)
.
Fréquence de Mise à Jour : Le SAR dépend du passage du satellite au-dessus d'une zone donnée, tandis que l'AIS est mis à jour en quasi temps réel
.
4. Unités de Mesure et Filtres
Caractéristique
SAR Vessel Detections
AIS Vessel Presence
Unité de mesure
Nombre de détections d'objets
Nombre d'heures de présence (une position par heure par navire)
Filtres spécifiques
Correspondance AIS (matched), longueur estimée (length_m), score de confiance (presence_score)
Type de navire (vessel_type), vitesse (speed), pavillon (flag)
Classification IA
Probabilité d'être un navire de pêche (neural_vessel_type)
Basée sur les registres et l'auto-déclaration AIS
En résumé, le dataset AIS Presence est idéal pour l'analyse globale du trafic maritime et de la gestion de flotte équipée
. À l'inverse, le SAR est l'outil privilégié pour la surveillance des zones reculées et la lutte contre la pêche illégale (IUU) en révélant les activités invisibles aux systèmes de suivi coopératifs

Les caractéristiques de fraîcheur et de couverture diffèrent significativement entre les jeux de données AIS Vessel Presence et SAR Vessel Detections. Bien que les deux soient disponibles via l'API 4Wings, ils reposent sur des sources et des cycles de mise à jour distincts.
1. Fraîcheur des données et délais
Il existe une différence de délai de publication entre les deux datasets :
AIS Vessel Presence : Les données sont disponibles de 2012 jusqu'à 96 heures (4 jours) avant la date actuelle
. La fréquence de mise à jour est décrite comme étant en quasi temps réel (near real-time)
.
SAR Vessel Detections : Les détections sont disponibles de 2017 jusqu'à 5 jours avant la date actuelle
. Contrairement à l'AIS, sa fréquence de mise à jour est dépendante du passage du satellite Sentinel-1 au-dessus d'une zone donnée
.
2. Couverture géographique
La portée géographique constitue la différence la plus marquée :
AIS Vessel Presence : Ce dataset offre une couverture mondiale pour tous les navires équipés de transpondeurs AIS
. Il n'est limité que par la capacité de réception des signaux par les constellations de satellites et les stations terrestres
.
SAR Vessel Detections : Sa couverture est limitée aux zones de balayage des satellites Sentinel-1
. Le radar ne traite pas la majeure partie de l'océan ouvert (open ocean) et se concentre principalement sur les eaux côtières
.
Exclusions SAR spécifiques : Le dataset SAR exclut volontairement les objets situés à moins de 1 km des côtes pour éviter les erreurs dues à la ligne de rivage, ainsi qu'une grande partie de l'Arctique et de l'Antarctique en raison des faux positifs générés par la glace de mer
.
3. Résumé technique comparatif
Caractéristique
AIS Vessel Presence
SAR Vessel Detections
Délai de publication
96 heures (4 jours)
5 jours
Mise à jour
Quasi temps réel
Dépendante du passage satellite
Couverture
Mondiale (navires AIS)
Zones côtières (balayage Sentinel-1)
Unité de mesure
Heures de présence
Nombre de détections
En conclusion, le dataset AIS Vessel Presence est plus "frais" et dispose d'une couverture beaucoup plus vaste que le SAR Vessel Detections, ce dernier étant un outil complémentaire spécialisé pour détecter l'activité dans les zones côtières, notamment pour les navires ne diffusant pas de signal AIS

Pour obtenir les données de détection SAR (Radar à synthèse d'ouverture) via les API version 3 (v3) de Global Fishing Watch, vous devez utiliser des points de terminaison (endpoints) et des identifiants de jeux de données spécifiques selon que vous recherchez des navires ou des infrastructures fixes.
1. Détections de navires (API 4Wings)
Les détections de navires industriels par SAR sont accessibles via l'API 4Wings (Map Visualization), qui permet l'analyse spatiotemporelle de données grillagées
.
Identifiant du dataset : public-global-sar-presence:latest
.
Endpoints principaux :
/v3/4wings/report : Pour générer des rapports agrégés en format CSV, JSON ou TIFF pour une région donnée
.
/v3/4wings/tile/heatmap/{z}/{x}/{y} : Pour obtenir des tuiles de carte au format MVT ou PNG
.
/v3/4wings/interaction/{z}/{x}/{y}/{cells} : Pour obtenir les détails d'une cellule spécifique (nombre de détections, ID du navire si apparié)
.
Filtres SAR spécifiques : Vous pouvez filtrer les résultats par matched (si détection appariée avec l'AIS), flag (pavillon), vessel_id, geartype (engin de pêche), neural_vessel_type (classification par IA) et shiptype
.
Disponibilité : Données de 2017 jusqu'à 5 jours avant la date actuelle
.
2. Infrastructures fixes offshore (API Datasets et Bulk Download)
Pour les structures fixes comme les plateformes pétrolières ou les parcs éoliens détectés par SAR, vous devez utiliser d'autres API
.
API Datasets (Visualisation) :
Dataset : public-fixed-infrastructure-filtered:latest
.
Endpoint : /v3/datasets/{dataset}/user-context-layers/{z}/{x}/{y} (format MVT)
.
Ce dataset est filtré pour exclure le "bruit" et les détections incertaines
.
API Bulk Download (Téléchargement massif) :
Dataset : public-fixed-infrastructure-data:latest
.
Endpoint : /v3/bulk-reports (requête POST)
.
Ce dataset contient toutes les données, y compris les détections potentiellement bruyantes
.
Disponibilité : Données de 2017 jusqu'à environ 3 mois avant la date actuelle
.
3. Méthodes d'accès et outils techniques
Authentification : Toutes les requêtes nécessitent un jeton d'accès (Bearer token) obtenu après création d'un compte sur le portail Global Fishing Watch
.
Format des paramètres : Dans la v3, tous les énumérations (enums) dans les paramètres de requête et le corps du message doivent être en MAJUSCULES (ex: DAILY, CSV)
.
SDK disponibles :
Python : Le package gfw-api-python-client (v1.0+) correspond directement à l'API v3 et inclut des fonctions intégrées pour les détections SAR
.
R : Le package gfwr a été mis à jour pour supporter la v3
.
Limites de débit : L'usage est limité à 50 000 requêtes par jour et 1,5 million par mois pour une utilisation non commerciale
.
En résumé, pour les navires, interrogez l'API 4Wings avec l'ID public-global-sar-presence:latest, et pour les infrastructures, utilisez l'API Datasets ou Bulk Download avec les identifiants dédiés

Dans l'API SatNOGS DB, l'endpoint exact qui retourne les éléments orbitaux à deux lignes (TLE) est /api/tle/ (ou l'URL complète https://db.satnogs.org/api/tle/)
. Cet endpoint permet de récupérer les données orbitales récentes nécessaires au suivi des satellites
.
Voici les différences principales entre cet endpoint et l'endpoint /api/satellites/ :
Nature des données :
/api/satellites/ : Cet endpoint retourne les métadonnées générales et les informations de communication du satellite
. Cela inclut son identifiant NORAD, son nom, son statut opérationnel (ex: "alive"), ainsi que les détails sur ses émetteurs (modes de modulation, fréquences de liaison descendante, etc.)
.
/api/tle/ : Il est spécifiquement dédié aux éléments orbitaux (orbital elements)
. Il fournit les deux lignes de données techniques utilisées par les logiciels de poursuite pour calculer la position exacte du satellite dans l'espace à un moment donné
.
Filtrage par NORAD ID :
L'API permet de cibler un satellite spécifique en utilisant son NORAD ID comme paramètre de requête pour obtenir ses TLE correspondants
.
Historique :
Il est important de noter que, bien que la base de données SatNOGS conserve les historiques, l'API publique standard ne propose pas actuellement d'endpoint pour les TLE historiques ; elle se concentre sur les données les plus récentes

D'après la documentation technique de Global Fishing Watch, il n'existe pas de mécanisme automatisé ou de documentation décrivant une procédure de traitement à la demande (on-demand processing) permettant à un utilisateur de déclencher manuellement le traitement d'une image Sentinel-1 pour une zone ou une date spécifique hors de la couverture actuelle.
Voici les points clés concernant la gestion de la couverture et les demandes personnalisées :
1. Dépendance structurelle aux priorités de mission
Le traitement des images SAR Sentinel-1 est réalisé de manière systématique par Global Fishing Watch, mais il est limité par deux facteurs :
Les acquisitions brutes : L'étendue et la fréquence des images disponibles dépendent exclusivement des priorités de mission de l'Agence spatiale européenne (ESA)
.
Le pipeline GFW : Bien que GFW traite les données à l'échelle mondiale, le radar ne balaie pas la majeure partie de l'océan ouvert, se concentrant sur les zones côtières
.
2. Distinction entre rapports personnalisés et traitement de données
Il ne faut pas confondre la capacité de définir une zone d'intérêt avec le traitement de nouvelles images :
Analyse de zones personnalisées : Les utilisateurs peuvent soumettre un polygone personnalisé (GeoJSON) via l'API 4Wings pour obtenir des statistiques (nombre de détections, heures de présence)
. Cependant, cette requête extrait uniquement des données qui ont déjà été traitées par le pipeline de détection automatique de GFW
.
Traitement de nouvelles dates/zones : Si une image existe dans les archives de l'ESA mais n'apparaît pas dans le dataset GFW, aucun outil en libre-service n'est documenté pour demander son intégration immédiate.
3. Canal de suggestion et retours
La seule procédure mentionnée pour influencer la couverture ou les données disponibles est le contact direct avec l'équipe technique :
Demandes de priorisation : La documentation précise explicitement : « Si vous avez besoin d'un [dataset] spécifique que vous aimeriez que nous priorisions, contactez-nous pour envoyer votre suggestion »
.
Adresse de contact : L'adresse mail dédiée aux questions relatives aux API et aux données est apis@globalfishingwatch.org
.
Amélioration du dataset : Étant donné que le dataset SAR Vessel Detections est en version 1, GFW sollicite les retours des utilisateurs pour améliorer les futures versions du modèle et la qualité des données
.
En résumé, si une zone ou une date spécifique manque dans le dataset SAR Vessel Detections, la démarche documentée consiste à contacter l'équipe par email pour suggérer son inclusion dans les futures mises à jour ou extensions du pipeline de traitement.

D'après la documentation technique de Global Fishing Watch, la "haute résolution spatiale" disponible via l'API 4Wings n'est pas aussi fine que 100 m. Elle est explicitement chiffrée à 0,01 degré, ce qui correspond à environ 1,1 km au niveau de l'équateur
.
Voici les détails précis concernant cette résolution et ses conséquences sur l'approximation de la position d'un navire :
1. Définition technique de la résolution "HIGH"
La documentation de l'API v3 (notamment pour l'endpoint /4wings/report) définit les deux niveaux de résolution comme suit :
LOW : Résolution au 10ème de degré (0,1°), soit environ 11 km
.
HIGH : Résolution au 100ème de degré (0,01°), soit environ 1,1 km
.
2. Précision du centre de la cellule
Comme vous l'aviez noté, les champs lat et lon retournés dans les rapports correspondent à la latitude et longitude du centre de la cellule de la grille
.
Avec une cellule de 0,01°, un navire peut se trouver n'importe où dans un carré d'environ 1,1 km de côté
.
L'erreur maximale de position par rapport au centre de la cellule est donc d'environ 780 mètres (distance entre le centre et un coin de la cellule).
3. Comparaison avec la précision réelle du radar SAR
L'approximation fournie par le centre de la cellule (1,1 km) est beaucoup plus grossière que les capacités intrinsèques du capteur et des données sources :
Résolution Sentinel-1 : Les images utilisées ont une résolution native d'environ 20 mètres
.
Grid de recherche : L'étude scientifique originale (Paolo et al., 2024) a utilisé une grille de 1/200° (environ 550 m) pour ses analyses, mais l'API publique agrège ces données à 0,01°
.
Précision des pixels : Les fichiers CSV bruts disponibles sur le portail de téléchargement (Portal Download) fournissent des positions lat/lon ponctuelles qui semblent correspondre à la détection réelle plutôt qu'à un centre de grille
.
Conclusion sur votre hypothèse
La position du centre de cellule en mode "HIGH" n'est pas une approximation acceptable pour une localisation précise à 100 m près. Elle introduit un flou d'environ 1 100 mètres, ce qui est bien supérieur à la taille d'une boîte de 5 pixels (qui représenterait environ 50 à 100 mètres selon le traitement SAR)
.
Pour obtenir une précision proche de la position réelle du navire (comparable à ce que ferait un calcul sur les pixels de l'image source), il est préférable d'utiliser le Data Download Portal plutôt que l'API 4Wings, car il fournit les détections individuelles avec leurs coordonnées lat et lon spécifiques

L'endpoint exact pour accéder au dataset AIS Vessel Presence dépend du type de données que vous souhaitez obtenir (rapports agrégés, tuiles de carte ou interactions locales), car ce jeu de données est intégré à l'API 4Wings (Map Visualization) de Global Fishing Watch
.
Voici les détails techniques pour y accéder via la version 3 de l'API :
1. Identifiant du Dataset
Pour toute requête, vous devez utiliser l'identifiant technique suivant
 :
Dataset ID : public-global-presence:latest
2. Endpoints principaux (v3)
Selon votre besoin, vous utiliserez l'un des points de terminaison de l'API 4Wings :
Pour générer des rapports (CSV, JSON, TIFF) :
POST https://gateway.api.globalfishingwatch.org/v3/4wings/report
GET https://gateway.api.globalfishingwatch.org/v3/4wings/report
Pour obtenir des tuiles de carte (Heatmap MVT ou PNG) :
GET https://gateway.api.globalfishingwatch.org/v3/4wings/tile/heatmap/{z}/{x}/{y}
Pour obtenir les détails d'une cellule spécifique (Interaction) :
GET https://gateway.api.globalfishingwatch.org/v3/4wings/interaction/{z}/{x}/{y}/{cells}
3. Filtres spécifiques disponibles
Contrairement au dataset de l'effort de pêche, l'AIS Vessel Presence permet de filtrer par
 :
flag (pavillon du navire)
vessel_type (type de navire : cargo, tanker, etc.)
speed (tranche de vitesse en nœuds)
vessel_id (identifiant unique GFW)
Note importante : Ce dataset ne fournit pas de trajectoires individuelles (tracks). Il comptabilise une position par heure et par navire pour visualiser la présence globale
. Pour des données spécifiques à un navire, il faut se tourner vers l'API Vessels

Oui, il est possible d'obtenir les dimensions des navires, mais la disponibilité de ces données dépend de l'API utilisée et de la source (AIS ou SAR).
Voici les détails selon la documentation technique :
1. Via l'API Vessels (Identité et Registres)
L'API Vessels v3 est le moyen le plus direct pour obtenir les caractéristiques physiques d'un navire connu.
Données de registres : Depuis l'intégration de nouvelles sources comme S&P Global (SNP) et TMT, l'API retourne des champs détaillés incluant la longueur (length), le tonnage brut (gross tonnage) et, pour certains navires, la profondeur (depthM)
.
Structure de la réponse : Ces informations se trouvent généralement dans l'objet registryInfo ou combinedSourcesInfo de la réponse API
.
2. Via les détections SAR (Radar)
Pour les navires détectés par satellite (notamment les "vaisseaux sombres"), les dimensions sont estimées par intelligence artificielle.
Estimation de la longueur : Le modèle d'apprentissage profond de Global Fishing Watch traite les images Sentinel-1 pour fournir une estimation de la longueur du navire en mètres (length_m)
.
Accessibilité :
Cette donnée est présente dans les fichiers CSV du Data Download Portal
.
Elle est également disponible via l'API Bulk Download
.
Attention : Le champ length_m n'est pas inclus dans les rapports agrégés de l'API 4Wings ou sur la carte interactive standard
.
3. Limitations et Fiabilité
Capacité de détection : La résolution du radar Sentinel-1 (~20 m) limite la détection des navires. La plupart des navires de moins de 15 mètres ne sont pas détectés
.
Précision de l'estimation : Pour le SAR, l'erreur quadratique moyenne (RMSE) du modèle d'estimation de la longueur est d'environ 21,9 mètres (soit environ un pixel de l'image source)
.
Erreurs de déclaration : Pour les données AIS, la documentation note que les dimensions peuvent être erronées si elles ont été mal saisies manuellement par les opérateurs dans les messages d'identité AIS
.
En résumé, pour obtenir des dimensions précises, privilégiez l'API Vessels (pour les navires identifiés via registres) ou l'API Bulk Download (pour les estimations de longueur sur les détections radar)
.