# **Upsell \- data model**

**Contact person design / decisions:** [Andrés Canelones Araujo](mailto:a.canelonesaraujo@coolblue.nl) / [Catarina Aguiso Pereira](mailto:c.aguisopereira@coolblue.nl)  
Design document: [Upsell Zone](https://docs.google.com/presentation/d/1Ju7iEqwTGKIQ6Mm9dyKpGNaF0qYUNNB7aIsBsU2dPIY/edit?slide=id.g475c065d71_1_0#slide=id.g475c065d71_1_0)

Scope of upsell groups

* Upsell is always within product type and brand combination, sometimes within a productline, if those are big enough. We will use clusters for this.  
  * Currently, clusters are likely to be too high-level, allowing for upsell to happen in contexts like ‘consumer laptops’, rather than ‘HP consumer laptops’. We will fix this with hierarchical clusters \+ inheritance  
  * Upsell across product lines has been historically hard to do in the upsell zone, which led to the creation of the product line upsell element under the image gallery. While this may not be the preferred solution going forward, it does show that upsell across product lines is probably better fixed elsewhere.

Considerations used

* We want to primarily focus on numeric or ordinal considerations that have a clear order in them.   
* They are always performance considerations (marked as such in the ground truth)  
* Brand specific technologies are out of scope  
* We provide max 3 considerations, in the right order. But we might decide that the upsell can be made with 1 or 2 considerations.  
  * Currently consideration orders are aimed at creating the best product descriptions, not upsell. Long term we will fix this with dedicated consideration orders for upsell. In the meantime we can provide the best upsell consideration order separately and use the consideration value order from the ground truth directly.  
    

Consideration values used

* We provide ranked values per consideration, so you can retrieve for example processors in their correct order  
* Sometimes, the right upsell might be 3 up from the current processor instead of 1, for example because the smaller upsell changes 10 other specs while going 2 steps does not change many other specs, thus being a lot ‘cleaner’.

Products allowed / price

* Points for the sorting step:  
  * Upsell steps should have reasonable price differences.   
  * Historically we often said: we should sell more expensive things, and it’s up to pricing/purchasing to make sure that those products are higher margin. Choices to make:   
    * Price of upsell always higher? (including or excluding discounts)  
    * Transaction margin of upsell always higher?

Base decisions \- upsell steps- as discussed in meetings with Pieter

* Upsell steps need to be reasonable. Not too big, not too small.   
* If a step in one consideration means that other specs change too, we can solve that with a conflict resolution screen. Our data model should give the most important ‘extra changes’ for the step we recommend  
* If too many things change at once, it’s not a valid upsell  
* The threshold is hard to define and should be tested

Translation of base decisions \- upsell steps

* We have 3 or less *upsell considerations*, defined manually  
* We have a list of the remainder of considerations from the ground truth  
* Per *upsell consideration* we always pick the value that is closest to our current value, always a step up (higher ranking) and adhering to the following rules. When choosing a different (higher) value for consideration X, other values can change.  
  * We allow all changes in values for upsell considerations with a lower ranking than consideration X, but for considerations with a higher ranking than consideration X a change in value downward can only go down one step. Changes upward are unlimited (they will both get a conflict resolution screen).  
  * If more than 2 (not upsell, but performance) considerations change negatively or positively we do not consider it as an option. (all performance ground truth considerations, not just upsell)  
  * The brand specific technology can never change.  
  * If there are no candidates, because the product already has the highest values  (without too much change to other values) then there are no upsell possibilities. We do not go outside the product type \+ brand combination.  
* Brand specific functions: the upsell options should at least have all the brand specific technologies the base model has. Extra options are allowed.

What can we provide

* A list of clusters, currently unordered, in the future hierarchical  
* Per cluster in scope, a purpose-made ordered list of considerations for upsell   
* Per consideration, the underlying values, and how they rank

**Fictional example**  
Washing Machines | Brand: AEG has 3 upsell considerations, with ranked values:

1. Fill weight \- 7kg, 8kg, 9kg  
2. RPM \- 1200, 1400, 1600  
3. Energy label \- C, B, A

Further Washing Machines | Brand: AEG has performance considerations

- Sort of steamcare: none, freshen up, less ironing, hygienic  
- Building quality: mid range, top range  
- Quick wash: no, yes

We start with a washing machine of 8kg, 1200 rpm, B energy label, no steamcare, white, mid range.  
For upsell consideration rpm we would preferably go to 1400\. If

- Energy label then goes to C or A, this is okay, because the upsell consideration is lower in the upsell consideration order  
- Fill weight changes to 7kg, this is **not** okay, because the upsell consideration rpm is lower than fill weight.  
- Fill weight changes to 9kg, this is okay, because the fill weight goes up  
- More than 2 other considerations (building quality, color or steamcare) change it is also not okay.  
- If there is no option for 1400, we try 1600\.

**Upsell considerations test cases**  
Washing Machines | Brand: AEG

- Vulgewicht  
- Energieklasse  
- Toerental

Laptops | Windows Consumer laptop (wij leggen focus op HP Pavilions, maar dit cluster bestaat nu niet)

- Processor  
- Intern werkgeheugen (RAM)  
- Totale opslagcapaciteit

Robot vacuums | Brand:Eufy

- Dweilklasse  
- ~~Zuig kracht~~

Mobile phones | Brand:Apple | iPhones | Test

- iPhone opslagcapaciteit

**Additional information Jake**

[Here’s a working prototype to gauge how the interaction looks](https://azalea-work-21286129.figma.site/product/967031/hp-pavilion-se-15-fd0956nd), make sure to use the cogwheel in the bottom left to set the upsell mode to “relative”

* Relative (with step up) simply allows a “double step up”: not just from i5 \-\> i7, but from i5 \-\> i7 \-\> i9

To me, the data product should provide an answer to the following question  
“Which product IDs do we want to show inside of the green zone, for this product ID given this context?”

*Context* in this case is whether a customer has *landed* on that specific product, or whether this product was *navigated to* from the collection element

* If a customer *landed* on that product, we should show the best possible set of options, given all the constraints that have been previously mentioned  
* If a customer *navigated to that product* from the collection element, this product should be added as context  
  * Hence, there are going to be situations in which two identical products can upsell to the same product:  
    * SKU \#1: i5 \- 16GB \- 512GB  
    * SKU \#2: i5 \- 16GB \- 512GB  
    * SKU \#3: i7 \- 16GB \- 512GB  
      * SKU \#3 can be accessed from both \#1 and \#2, but \#1/\#2 can only be accessed from \#3 whenever someone came from \#1/\#2  
      * \#1 \-\> \#3: you see \#1 as the option  
      * \#2 \-\> \#3: you see \#2 as the option  
  * **This means that the group of products that can be accessed from any product is highly dependent on this context, and needs to be taken into consideration inside of the data model**

I think the way to go here is:

1. Figure out what the total eligible set of products is that one *could navigate to* based solely on the property constraints (top 3 considerations, steps not too big, no other considerations changing, etc)  
2. Per potential step-up consideration value, decide which products is objectively the best product to navigate to  
3. This would then be a “base set” of products:  
   1. Main product **123456** \- previous product: None  
      1. Candidate up \#1 \- processor 	\- **958272**, candidate down: none  
      2. Candidate up \#2 \- RAM 		\- 472273, candidate down: none  
      3. Candidate up \#3 \- Storage 		\- 844924, candidate down: none  
4. Then, per potential candidate we can provide context if navigated to that product  
   1. Main product **958272** \- previous product: **123456**  
      1. Candidate up \#1 \- processor 	\- None, candidate down: **123456**  
      2. Candidate up \#2 \- RAM 		\- **472273**, candidate down: none  
      3. Candidate up \#3 \- Storage 		\- 844924, candidate down: none  
         1. Note: I chose for the non step-up variant, thus no extra processor candidate would be available to move up towards  
   2. We do need to account for the cases in which one steps up on a different spec as well, giving two products as context  
   3. Main product **472273** \- previous product: 123456, **958272**  
      1. Candidate up \#1 \- processor 	\- None, candidate down: **123456**  
      2. Candidate up \#2 \- RAM 		\- None, candidate down: **958272**  
      3. Candidate up \#3 \- Storage 		\- 844924, candidate down: none
