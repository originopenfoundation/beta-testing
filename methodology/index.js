'use strict';
function evaluate(question, resources, lang, copy, priorUserInput=[]) {
  const supplied=[...priorUserInput,question].filter(Boolean).slice(-6);
  const evidence=supplied.length>0;
  const used=resources.map(x=>x.resource.title);
  return { status:copy.notValidated, user_provided_information:evidence?supplied:[], known_facts:[], methodological_assessment:copy.evidence,
    potential_governance_gaps:[], missing_evidence:[copy.missing], relevant_methodologies:used, next_steps:[copy.missing],
    trace:{methodologies_used:used, governed_spaces:[], assessment_status:copy.notValidated, evidence_gaps:[copy.missing]} };
}
module.exports={evaluate};
