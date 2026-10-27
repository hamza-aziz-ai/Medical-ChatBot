<template>
  <aside
    class="about"
    aria-labelledby="about-title"
  >
    <h2 id="about-title">
      About
    </h2>
    <p>
      Mr. Healthcare answers basic questions about diseases and symptoms from a knowledge graph of about 650 diseases stored in Neo4j. It is a student prototype for local use, first built during the COVID-19 lockdowns.
    </p>

    <dl class="facts">
      <div>
        <dt>658</dt>
        <dd>diseases</dd>
      </div>
      <div>
        <dt>1,772</dt>
        <dd>symptoms</dd>
      </div>
      <div>
        <dt>43</dt>
        <dd>departments</dd>
      </div>
    </dl>

    <details open>
      <summary>What you can ask</summary>
      <ul>
        <li>Symptoms of a disease, or diseases with a symptom</li>
        <li>Causes and prevention</li>
        <li>Treatments and complications</li>
        <li>A short description of a disease</li>
      </ul>
    </details>

    <details>
      <summary>How it works</summary>
      <ul>
        <li>Disease and symptom names are found in your question as whole words.</li>
        <li>A language model reads what you are asking, choosing only among the names found; if it is unavailable or unsure, keywords decide.</li>
        <li>Questions are processed on this site's servers and may pass through external hosting, network and AI services; answers come only from the knowledge graph.</li>
        <li>The matching facts are looked up in the graph and returned as plain sentences.</li>
        <li>If the graph has no answer, or you ask about treatment duration, cure probability or who is susceptible, Mr. Healthcare says it cannot answer.</li>
      </ul>
    </details>

    <details>
      <summary>Limits</summary>
      <ul>
        <li>The data's source and clinical review are unknown, and some records were left out because they conflicted.</li>
        <li>Symptom answers list diseases recorded with that symptom. They are not a diagnosis.</li>
        <li>Questions phrased in other ways may not be understood.</li>
      </ul>
    </details>
  </aside>
</template>

<script>
export default {
  name: "MedicalChatbot",
};
</script>
