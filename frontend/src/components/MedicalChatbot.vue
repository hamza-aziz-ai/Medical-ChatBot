<template>
  <aside
    class="about"
    aria-labelledby="about-title"
  >
    <h2 id="about-title">
      About
    </h2>
    <p>
      Mr. Healthcare answers basic questions about diseases and symptoms from a knowledge graph of about 650 diseases
      stored in Neo4j. It is a student prototype for local use, first built during the COVID-19 lockdowns.
    </p>

    <h3>How it works</h3>
    <ul>
      <li>Disease and symptom names are found in your question as whole words.</li>
      <li>Keywords decide what you are asking: symptoms, causes, prevention, treatments, complications or a description.</li>
      <li>The matching facts are looked up in the graph and returned as plain sentences.</li>
      <li>
        If the graph has no answer, or you ask about treatment duration, cure probability or who is susceptible,
        Mr. Healthcare says it cannot answer.
      </li>
    </ul>

    <h3>Limits</h3>
    <ul>
      <li>The data's source and clinical review are unknown, and some records were left out because they conflicted.</li>
      <li>Symptom answers list diseases recorded with that symptom. They are not a diagnosis.</li>
      <li>Questions phrased in other ways may not be understood.</li>
    </ul>
  </aside>
</template>

<script>
export default {
  name: "MedicalChatbot",
};
</script>
