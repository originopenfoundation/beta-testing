'use strict';
const assess=[/\b(assess|evaluate|adequate|gap|should we|should who|validate|evidence do|risk|approve|authority|governance|decision)\b/i,
 /\b(prüf|bewert|beurteil|lücke|sollten wir|wer sollte|validier|nachweis|risiko|genehmig|zuständigkeit|governance)\b/i,
 /\b(évalu|analyser|lacune|devrions-nous|qui devrait|valider|preuve|risque|décision)\b/i,
 /\b(valuta|lacuna|dovremmo|chi dovrebbe|prova|rischio|decidere|autorità|governance)\b/i,
 /\b(evalúa|evalua|brecha|deberíamos|quién debería|evidencia|riesgo|decidir|gobernanza)\b/i,
 /\b(avalie|avaliar|lacuna|deveríamos|quem deve|evidência|risco|decisão|governança)\b/i,
 /[\u4e00-\u9fff]*(评估|应该|风险|决策|证据|治理)/u,
 /[\u3040-\u30ff]*(評価|すべき|リスク|証拠|決定|ガバナンス)/u,
 /[\uac00-\ud7af]*(평가|해야|위험|결정|증거|거버넌스)/u,
 /\b(posúď|posúdiť|medzera|mali by|kto by mal|dôkaz|riziko|rozhodnut|riadenie|zodpovednosť)\b/i];
function classify(question, requested='auto') { if(requested==='assessment')return 'methodology_application'; if(requested==='knowledge')return 'knowledge_retrieval'; return assess.some(r=>r.test(question))?'methodology_application':'knowledge_retrieval'; }
module.exports={classify};
