from __future__ import annotations
import asyncio, json
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from services.ai_service import _env_key, get_ai_settings

MODE_INSTRUCTIONS = {
    "hint": "Donne un indice progressif. Ne donne pas immédiatement le résultat final. Pose une petite question qui aide l'élève à avancer.",
    "method": "Explique la méthode étape par étape avec un mini exemple différent. Termine par ce que l'élève doit faire ensuite sur son exercice.",
    "explain": "Explique le concept simplement, avec vocabulaire adapté à la classe et un exemple court. Vérifie la compréhension avec une question.",
    "check": "Analyse la réponse proposée par l'élève. Dis ce qui est correct, ce qui doit être corrigé, et pourquoi. Ne remplace pas tout son travail sans explication.",
    "quiz": "Crée un quiz progressif avec questions courtes. Donne les réponses dans une section séparée à la fin pour permettre l'auto-correction.",
    "flashcards": "Crée des cartes de révision sous la forme Question :: Réponse, une carte par ligne, adaptées au niveau de l'élève.",
    "revision": "Construis une fiche de révision structurée : notions clés, méthode, erreurs fréquentes, exemple et mini-test final.",
    "similar": "Crée un exercice similaire mais avec des données différentes. Ne donne la correction qu'après une séparation claire.",
}


def _local_tutor(subject, mode, prompt, answer, user):
    guide = {
        "hint": "Commence par repérer les données importantes et ce que la consigne te demande. Écris une première étape, puis vérifie si elle te rapproche du résultat.",
        "method": "1) Reformule la consigne. 2) Liste les informations utiles. 3) Choisis la règle ou méthode. 4) Fais le calcul/raisonnement. 5) Vérifie l'unité ou la cohérence.",
        "explain": "Je peux t'aider à comprendre le cours. Pour une explication vraiment adaptée à ton exercice, active le fournisseur OpenAI dans l'administration de PiChat.",
        "check": "Compare ta réponse à la consigne : as-tu répondu à toutes les parties, justifié les étapes et vérifié le résultat ? Le mode OpenAI peut faire une vérification détaillée.",
        "quiz": "Quiz express : 1) Reformule la notion. 2) Donne un exemple. 3) Explique l'erreur la plus fréquente. Les réponses sont à vérifier dans ton cours.",
        "flashcards": "Notion principale :: définition simple\nMéthode :: étapes à appliquer\nVérification :: question à se poser avant de rendre le travail",
        "revision": "Fiche express : définition, méthode, exemple, erreur fréquente et question de vérification. Active OpenAI pour une fiche vraiment adaptée au sujet fourni.",
        "similar": "Crée toi-même une variante en changeant les nombres, les personnages ou le contexte, puis applique exactement la même méthode.",
    }.get(mode, "Commence par reformuler la question et repérer les informations utiles.")
    return {"answer": f"📚 {subject} — {guide}", "provider": "local", "model": "local", "mode": mode}


def _openai_tutor_sync(subject, mode, prompt, answer, user, settings):
    key=_env_key()
    if not key:
        return _local_tutor(subject,mode,prompt,answer,user)
    instructions = f"""Tu es PiTutor, l'assistant devoirs de PiChat pour un élève de classe {user.get('class_code') or 'non précisée'}.
Matière: {subject}.
Mode pédagogique: {mode}. {MODE_INSTRUCTIONS[mode]}
Réponds en français, clairement et avec bienveillance. Adapte le niveau à un collégien/lycéen selon la classe fournie.
Tu es un tuteur: favorise la compréhension, les indices et la méthode plutôt que de fournir une réponse brute à copier.
Ne demande ni n'expose de données personnelles. Si le sujet est sensible ou dangereux, reste prudent et oriente vers un adulte/enseignant approprié.
Indique brièvement quand une information doit être vérifiée dans le cours ou par l'enseignant."""
    user_input = f"Exercice / question:\n{prompt}"
    if answer.strip():
        user_input += f"\n\nRéponse de l'élève à vérifier:\n{answer.strip()}"
    payload={"model":settings.get("model") or "gpt-5.6","instructions":instructions,"input":user_input,"max_output_tokens":700}
    req=urlrequest.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode('utf-8'),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urlrequest.urlopen(req,timeout=45) as resp: data=json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        try: detail=json.loads(e.read().decode('utf-8')).get('error',{}).get('message','')
        except Exception: detail=''
        return {"answer":"⚠️ L'IA n'a pas pu répondre"+(f" : {detail[:180]}" if detail else "."),"provider":"openai","model":settings.get("model"),"mode":mode}
    except URLError:
        return {"answer":"⚠️ Impossible de joindre le service IA. Vérifie la connexion Internet.","provider":"openai","model":settings.get("model"),"mode":mode}
    texts=[]
    for item in data.get('output',[]):
        if item.get('type')!='message': continue
        for part in item.get('content',[]):
            if part.get('type')=='output_text' and part.get('text'): texts.append(part['text'])
    text='\n'.join(texts).strip() or "Je n'ai pas réussi à produire une réponse utile. Reformule la question."
    return {"answer":text[:6000],"provider":"openai","model":settings.get("model"),"mode":mode}


async def tutor_answer(subject, mode, prompt, answer, user):
    settings=get_ai_settings()
    if settings.get("provider")=="openai" and settings.get("api_key_configured"):
        return await asyncio.to_thread(_openai_tutor_sync,subject,mode,prompt,answer,user,settings)
    return _local_tutor(subject,mode,prompt,answer,user)
