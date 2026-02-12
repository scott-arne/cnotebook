import marimo

__generated_with = "0.19.7"
app = marimo.App(width="medium")


@app.cell
def _():
    import pandas as pd
    import oepandas as oepd
    from cnotebook import MolGrid
    from sklearn.cluster import HDBSCAN
    import marimo as mo
    return HDBSCAN, mo, oepd


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Table of Contents

    - [Viewing Clusters](#viewing-clusters)
      - [Step 1: Create Fingerprints](#step-1-create-fingerprints)
      - [Step 2: Molecular Clustering](#step-2-molecular-clustering)
    - [Step 3: Visualize](#step-3-visualize)
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    # Viewing Clusters

    The ```cnotebook.MolGrid``` class and ```cnotebook.molgrid``` function both contain a ```cluster``` parameter to enable convenient cluster browsing. Let's see it in action with a simple example.

    The file ```assets/two_series.sdf``` has two very different series of molecules from the following publications:

    > AT Ginnetti, DV Paone, KK Nanda, J Ling, M Busuek, SA Johnson, J Lu, SM Soisson, R Robinson, J Fisher, A Webber, G Wesolowski, B Ma, L Duong, S Carroll, CS Burgey, SJ Stachel. Lead optimization of cathepsin K inhibitors for the treatment of Osteoarthritis. Bioorg Med Chem Lett, 2022. 74: 128927

    > S Stachel, A Ginnetti, SA Johnson, P Cramer, Y Wang, M Bukhtiyarova, D Krosky, C Stump, D Hurzy, KA Schlegel, A Cooke, S Allen, G O'Donnell, M Ziebell, G Parthasarathy, K Getty, T Ho, Y Ou, A Jovanovska, S Carroll, M Pausch, K Lumb, S Mosser, B Voleti, D Klein, S Soisson, C Zerbinatti, P Coleman. Identification of Potent Inhibitors of the Sortilin-Progranulin Interaction. BMCL, 2020. 30(17): 127403

    Let's perform some simple molecular clustering and see how well we separate them.
    """)
    return


@app.cell
def _(oepd):
    df = oepd.read_sdf("assets/two_series.sdf")
    df.tail()
    return (df,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Step 1: Create Fingerprints

    You can use either of the following two methods to create fingerprint series from a molecule series, which use the [OpenEye GraphSim Toolkit](https://docs.eyesopen.com/toolkits/python/graphsimtk/index.html) under-the-hood:

    * ```Series.chem.create_fingerprints(...)```: Creates a series of ```OEFingerPrint``` objects. The series has a dtype of ```FingerprintDtype```.
    * ```Series.chem.create_numpy_fingerprints(...)```: Creates a series of NumPy boolean array objects. The series has a dtype of ```object```.

    The following creates ECFP4-like circular fingerprints as NumPy boolean arrays, convenient for clustering using Scikit-Learn:
    """)
    return


@app.cell
def _(df):
    df["Fingerprint"] = df.Molecule.chem.create_numpy_fingerprints(
        "Circular",  # Path, Tree, LINGO, MACCS
        num_bits=2048,
        min_distance=0,  # Radius for circular fingerprints
        max_distance=2,  # Radius for circular fingerprints
        atom_type="DefaultCircularAtom",  # Also accepts oegraphsim.OEFPAtomType_ values
        bond_type="DefaultCircularBond"  # Also accepts oegraphsim.OEFPBondType_ values
    )

    df.head()
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Step 2: Molecular Clustering

    Let's use the [HDBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html) method to cluster, since it usually does a pretty decent job and requires very little parameterization.
    """)
    return


@app.cell
def _(HDBSCAN, df):
    _clusterer = HDBSCAN(copy=False)
    result = _clusterer.fit(df.Fingerprint.to_list())

    # We can inspect the result if we like
    result
    return (result,)


@app.cell
def _(df, result):
    # Assign the cluster labels
    df["Cluster"] = result.labels_

    df.head()
    return


@app.cell
def _(mo):
    mo.md(r"""
    # Step 3: Visualize

    The best part, let's do some clustering visualization!

    **What you should see and try:**

    * A "Cluster" box with dropdown. You can select the clusters to visualize (unique values of "Cluster" in the above DataFrame)
    * Dismissable pillboxes when you select one or multiple clusters
    * If you "Select All" in the "..." menu while filtering on a cluster (or clusters), it will only select from what is filtered.

    /// note |
    The grid does not save state between notebook executions. You'll lose your previous selections and filtering state when the notebook is restarted. Remember to save them! It is possible that this will be enabled in a future update.
    ///
    """)
    return


@app.cell
def _(df):
    grid = df.chem.molgrid(
        "Molecule",
        cluster="Cluster"
    )

    grid.display()
    return


if __name__ == "__main__":
    app.run()
